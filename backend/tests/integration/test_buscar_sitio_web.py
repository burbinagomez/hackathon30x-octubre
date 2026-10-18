"""Buscador de sitio web (006, enmienda 2026-10-18) de punta a punta: Postgres real, API real, cifrado y costos reales.
Una empresa del RUES (jurídica, con NIT) sin web ni teléfono: el buscador halla su sitio, `sitio_web` saca el teléfono y
el lead sale en el export. Transporte y DNS falsos: sin red. Datos sintéticos."""
import csv
import io
import logging
from datetime import UTC, datetime

import httpx

from app.api.enriquecimiento import tanda
from sqlalchemy import text

from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

NIT = "900123456"
TEL_VISIBLE = "+57 601 555 0188"
TEL_EXPORT = "576015550188"  # el adaptador lo normaliza a dígitos con 57
PUBLICA = "93.184.216.34"


def _rues(nombre: str, nit: str = NIT) -> EmpresaCruda:
    return EmpresaCruda(pais="CO", nombre=nombre, fuente="datos_gov_co_rues", url_origen="https://ejemplo.invalid/rues",
                        as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("5229", "CIIU"), id_fiscal=nit,
                        tipo_titular="juridica", ciudad="Cali")


def _sembrar(repo, busqueda, empresa):
    lead_id, _ = repo.obtener_o_crear_lead(empresa, "cc-by-sa")
    repo.agregar_lead_fuente(lead_id, busqueda, empresa, "cc-by-sa")
    return lead_id


class Mundo:
    """Sirve `paginas` por Host; todo lo demás es 404 y su DNS no resuelve."""

    def __init__(self, paginas: dict[str, str]):
        self.paginas, self.pedidos = paginas, []

    def transporte(self, request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        self.pedidos.append((host, request.url.path))
        if request.url.path == "/robots.txt" or host not in self.paginas:
            return httpx.Response(404)
        return httpx.Response(200, text=self.paginas[host], headers={"content-type": "text/html; charset=utf-8"})

    def dns(self, host: str) -> list[str]:
        if host not in self.paginas:
            raise OSError("Name or service not known")
        return [PUBLICA]


def _correr(cliente, usuarios, mundo, *leads):
    estado = cliente.app.state
    estado.transporte_http = httpx.MockTransport(mundo.transporte)
    estado.resolver_dns = mundo.dns
    repo = RepositorioLeadsPostgres(estado.engine, usuarios["tenant_a"], estado.cifrador)
    busqueda = repo.crear_busqueda(CriteriosICP("CO", {}))
    ids = [_sembrar(repo, busqueda, e) for e in leads]
    return busqueda, ids, tanda(estado, usuarios["tenant_a"], busqueda)  # la tanda del proceso en segundo plano


def _lead(admin, lead_id):
    with admin.connect() as c:
        return c.execute(text("SELECT web, telefono_cifrado, telefono_canal, contactable, razon_no_contactable "
                              "FROM leads WHERE id = :id"), {"id": lead_id}).one()


def test_lead_del_rues_sin_web_queda_con_web_telefono_cifrado_contactable_y_en_el_export(cliente, admin, usuarios, caplog):  # noqa: F811
    caplog.set_level(logging.DEBUG)
    mundo = Mundo({"grupoprocessa.com.co": f"<html><body>Grupo Procesos NIT 900.123.456-7 Tel {TEL_VISIBLE}</body></html>"})

    busqueda, (lead,), r = _correr(cliente, usuarios, mundo, _rues("GRUPO PROCESSA S.A.S"))

    assert (r.procesados, r.contactables) == (1, 1)
    fila = _lead(admin, lead)
    assert (fila.web, fila.contactable, fila.razon_no_contactable, fila.telefono_canal) == (
        "grupoprocessa.com.co", True, None, "sitio_web")
    assert fila.telefono_cifrado is not None and b"555" not in bytes(fila.telefono_cifrado)
    export = cliente.get("/calificaciones/exportar", headers=_bearer(usuarios["a"]))
    filas = list(csv.DictReader(io.StringIO(export.text)))
    assert [(f["lead_id"], f["to_number"]) for f in filas] == [(str(lead), TEL_EXPORT)]
    for texto in (repr(r), caplog.text):
        assert "555" not in texto and "grupoprocessa" not in texto.lower()


def test_la_evidencia_queda_en_cumplimiento_sin_contacto(cliente, admin, usuarios):  # noqa: F811
    mundo = Mundo({"grupoprocessa.com.co": f"<html><body>NIT {NIT} Tel {TEL_VISIBLE}</body></html>"})

    _, (lead,), _ = _correr(cliente, usuarios, mundo, _rues("GRUPO PROCESSA SAS"))

    with admin.connect() as c:
        solicitudes = c.execute(text("SELECT solicitudes FROM cumplimiento WHERE lead_id = :id"), {"id": lead}).scalar()
    (entrada,) = [s for s in solicitudes if s["tipo"] == "sitio_web_encontrado"]
    assert (entrada["url"], entrada["motivo"], entrada["fuente"]) == (
        "https://grupoprocessa.com.co/", "nit", "dominio_por_razon_social")
    assert "ts" in entrada and "555" not in str(solicitudes)


def test_una_pagina_que_no_es_de_la_empresa_no_se_acepta(cliente, admin, usuarios):  # noqa: F811
    mundo = Mundo({"grupoprocessa.com.co": f"<html><body>Dominio en venta. Tel {TEL_VISIBLE}</body></html>"})

    _, (lead,), r = _correr(cliente, usuarios, mundo, _rues("GRUPO PROCESSA SAS"))

    fila = _lead(admin, lead)
    assert (fila.web, fila.telefono_cifrado, fila.contactable, fila.razon_no_contactable) == (
        None, None, False, "sin_canal_publicado")
    with admin.connect() as c:
        assert c.execute(text("SELECT solicitudes FROM cumplimiento WHERE lead_id = :id"), {"id": lead}).scalar() == []
    assert ("grupoprocessa.com.co", "/") in mundo.pedidos and all(p[1] in ("/",) for p in mundo.pedidos)  # solo la portada


def test_los_costos_van_al_lead_y_son_web_fetch(cliente, admin, usuarios):  # noqa: F811
    mundo = Mundo({"grupoprocessa.com.co": f"<html><body>NIT {NIT} Tel {TEL_VISIBLE}</body></html>"})

    _, (lead,), _ = _correr(cliente, usuarios, mundo, _rues("GRUPO PROCESSA SAS"))

    with admin.connect() as c:
        filas = c.execute(text("SELECT tipo, lead_id, lote_id, proveedor FROM costos WHERE tenant_id = :t"),
                          {"t": usuarios["tenant_a"]}).all()
    assert len(filas) == len(mundo.pedidos) and len(filas) >= 3  # portada del buscador + robots + portada de sitio_web
    assert {(f.tipo, f.lead_id, f.lote_id, f.proveedor) for f in filas} == {("web_fetch", lead, None, "web")}


def test_dns_que_no_resuelve_no_genera_ni_un_request_ni_un_costo(cliente, admin, usuarios):  # noqa: F811
    mundo = Mundo({})

    _, (lead,), r = _correr(cliente, usuarios, mundo, _rues("GRUPO PROCESSA SAS"))

    assert r.procesados == 1 and mundo.pedidos == []
    with admin.connect() as c:
        assert c.execute(text("SELECT count(*) FROM costos WHERE tenant_id = :t"), {"t": usuarios["tenant_a"]}).scalar() == 0
    assert _lead(admin, lead).web is None


def test_un_lead_con_web_de_osm_no_se_busca_y_no_deja_evidencia(cliente, admin, usuarios):  # noqa: F811
    mundo = Mundo({"andinos.invalid": f"<html><body>Tel {TEL_VISIBLE}</body></html>"})
    con_web = EmpresaCruda(pais="CO", nombre="Andinos SAS", fuente="osm_overpass", url_origen="https://ejemplo.invalid/o",
                           as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("5229", "CIIU"), id_fiscal="900777888",
                           tipo_titular="juridica", ciudad="Cali", web="andinos.invalid")

    _, (lead,), _ = _correr(cliente, usuarios, mundo, con_web)

    assert {h for h, _ in mundo.pedidos} == {"andinos.invalid"}
    with admin.connect() as c:
        assert c.execute(text("SELECT solicitudes FROM cumplimiento WHERE lead_id = :id"), {"id": lead}).scalar() == []


def test_una_tanda_mezcla_leads_con_y_sin_sitio(cliente, admin, usuarios):  # noqa: F811
    mundo = Mundo({"grupoprocessa.com.co": f"<html><body>NIT {NIT} Tel {TEL_VISIBLE}</body></html>"})

    _, (con, sin), r = _correr(cliente, usuarios, mundo, _rues("GRUPO PROCESSA SAS"), _rues("OTRA EMPRESA SAS", "900555444"))

    assert (r.procesados, r.contactables, r.pendientes) == (2, 1, 0)
    assert _lead(admin, con).contactable is True and _lead(admin, sin).web is None
