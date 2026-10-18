"""Verificación de titular por nombre + ciudad contra el RUES (006, enmienda 2026-10-18): Postgres real, repo, costos y
cifrado de verdad; datos.gov.co con transporte falso. Sin red. Datos sintéticos."""
import csv
import io
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text

from app.composicion import adaptadores_enriquecer, cargar_tarifas
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from app.modulos.enriquecimiento.aplicacion.enriquecer_lead import EnriquecerLead
from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

TELEFONO = "+57 601 555 0142"  # sintético
SAS = "SOCIEDADES POR ACCIONES SIMPLIFICADAS SAS"
AJUSTES = SimpleNamespace(typesafe_api_key=None, typesafe_url=None, datos_gov_co_url=None, datos_gov_co_app_token=None)


def _fila(nit, razon, camara="04"):
    return {"nit": nit, "digito_verificacion": "1", "razon_social": razon, "cod_ciiu_act_econ_pri": "4923",
            "codigo_camara": camara, "organizacion_juridica": SAS, "estado_matricula": "ACTIVA", "fecha_renovacion": "20260410"}


def _rues(por_nombre: dict[str, list[dict] | int], naturales: dict[str, int] | None = None):
    """Responde según el nombre buscado (en el $where). Un entero es un status de error."""
    pedidas = []
    naturales = naturales or {}

    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.host != "www.datos.gov.co":
            return httpx.Response(404)
        pedidas.append(request)
        if "count(" in request.url.params["$select"]:
            return httpx.Response(200, json=[{"count": str(naturales.get(request.url.params["$where"].split("'")[1].strip("%"), 0))}])
        donde = request.url.params["$where"]
        for clave, respuesta in por_nombre.items():
            if f"'%{clave}%'" in donde:
                return httpx.Response(respuesta, json={}) if isinstance(respuesta, int) else httpx.Response(200, json=respuesta)
        return httpx.Response(200, json=[])

    return httpx.MockTransport(responder), pedidas


def _empresa(nombre: str, ciudad: str | None = "Bogotá") -> EmpresaCruda:
    return EmpresaCruda(pais="CO", nombre=nombre, fuente="osm_overpass", url_origen="https://ejemplo.invalid/osm",
                        as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("4923", "CIIU"), ciudad=ciudad)


def _sembrar(repo, admin, cifrador, tenant, busqueda: UUID, nombre: str, ciudad: str | None = "Bogotá",
             telefono: str | None = TELEFONO) -> UUID:
    """Un lead de OSM: tipo desconocido, con teléfono publicado en OSM."""
    e = _empresa(nombre, ciudad)
    lead_id, _ = repo.obtener_o_crear_lead(e, "odbl")
    repo.agregar_lead_fuente(lead_id, busqueda, e, "odbl")
    if telefono:
        with admin.begin() as c:
            c.execute(text("UPDATE leads SET telefono_cifrado = :t, telefono_canal = 'osm_contacto' WHERE id = :id"),
                      {"t": cifrador.cifrar("telefono_cifrado", telefono, tenant, lead_id), "id": lead_id})
    return lead_id


@pytest.fixture
def mundo(rt, admin, tenants, cifrador):
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    return repo, PostgresCostos(rt, tenants["a"]), repo.crear_busqueda(CriteriosICP("CO", {}))


def _enriquecer(repo, costos, busqueda, transporte):
    verificador, enriquecedor, clasificador = adaptadores_enriquecer(AJUSTES, costos, cargar_tarifas(), transporte)
    return EnriquecerLead(repo, verificador, enriquecedor, clasificador).ejecutar(busqueda)


def _lead(admin, lead_id):
    with admin.connect() as c:
        return c.execute(text("SELECT tipo_titular, contactable, razon_no_contactable, nombre FROM leads WHERE id = :id"),
                         {"id": lead_id}).one()


def _solicitudes(admin, lead_id) -> list[dict]:
    with admin.connect() as c:
        return c.execute(text("SELECT solicitudes FROM cumplimiento WHERE lead_id = :id"), {"id": lead_id}).scalar()


def test_match_unico_sube_a_juridica_y_deja_la_evidencia_en_cumplimiento(admin, tenants, cifrador, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Transportes Andinos")
    transporte, _ = _rues({"TRANSPORTES ANDINOS": [_fila("900111222", "TRANSPORTES ANDINOS S.A.S.")]})

    _enriquecer(repo, costos, busqueda, transporte)

    assert _lead(admin, lead)[:3] == ("juridica", True, None)
    (entrada,) = _solicitudes(admin, lead)
    assert {k: v for k, v in entrada.items() if k != "ts"} == {
        "tipo": "paso_a_claro", "motivo": "match_unico", "fuente": "datos_gov_co_rues", "dataset": "c82u-588k",
        "nit": "900111222", "razon_social": "TRANSPORTES ANDINOS S.A.S.", "municipio": "Bogotá"}
    assert "ts" in entrada
    assert TELEFONO not in json.dumps(entrada) and "555" not in json.dumps(entrada)  # nunca el contacto


def test_sin_match_tambien_deja_constancia_y_el_lead_no_es_contactable(admin, tenants, cifrador, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Transportes Andinos")
    transporte, _ = _rues({"TRANSPORTES ANDINOS": [_fila("900111222", "TRANSPORTES ANDINOS S.A.S.", camara="14")]})  # Girardot

    _enriquecer(repo, costos, busqueda, transporte)

    assert _lead(admin, lead)[:3] == ("desconocido", False, "persona_natural")
    (entrada,) = _solicitudes(admin, lead)
    assert {k: v for k, v in entrada.items() if k != "ts"} == {
        "tipo": "verificacion_titular", "motivo": "sin_match", "fuente": "datos_gov_co_rues", "dataset": "c82u-588k"}


def test_ambiguo_guarda_cuantos_candidatos_y_ningun_nit(admin, tenants, cifrador, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Transportes Andinos")
    transporte, _ = _rues({"TRANSPORTES ANDINOS": [_fila("900111222", "TRANSPORTES ANDINOS SAS"),
                                                   _fila("900333444", "TRANSPORTES ANDINOS LTDA")]})

    _enriquecer(repo, costos, busqueda, transporte)

    (entrada,) = _solicitudes(admin, lead)
    assert (entrada["motivo"], entrada["candidatos"]) == ("ambiguo", 2) and "nit" not in entrada
    assert _lead(admin, lead)[0] == "desconocido"


def test_sin_ciudad_no_consulta_ni_cobra(admin, tenants, cifrador, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Transportes Andinos", ciudad=None)
    transporte, pedidas = _rues({"TRANSPORTES ANDINOS": [_fila("900111222", "TRANSPORTES ANDINOS S.A.S.")]})

    _enriquecer(repo, costos, busqueda, transporte)

    assert pedidas == [] and _lead(admin, lead)[0] == "desconocido"
    assert _solicitudes(admin, lead)[0]["motivo"] == "sin_ciudad"
    with admin.connect() as c:
        assert c.execute(text("SELECT count(*) FROM costos WHERE tenant_id = :t"), {"t": tenants["a"]}).scalar() == 0


def test_cada_consulta_queda_en_costos_con_su_lead(admin, tenants, cifrador, mundo):
    repo, costos, busqueda = mundo
    uno = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Transportes Andinos")
    dos = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Carga Rapida")
    transporte, pedidas = _rues({"TRANSPORTES ANDINOS": [_fila("900111222", "TRANSPORTES ANDINOS SAS")]})

    _enriquecer(repo, costos, busqueda, transporte)

    with admin.connect() as c:
        filas = c.execute(text("SELECT tipo, proveedor, fuente, lead_id, lote_id, moneda, gratis, costo_unitario FROM costos "
                               "WHERE tenant_id = :t"), {"t": tenants["a"]}).all()
    assert len(pedidas) == len(filas) == 3  # uno: búsqueda + conteo de naturales; dos: solo la búsqueda (sin match)
    assert sorted(str(f.lead_id) for f in filas) == sorted(map(str, [uno, uno, dos]))
    assert {(f.tipo, f.proveedor, f.fuente, f.lote_id, f.moneda) for f in filas} == {
        ("socrata_descarga", "datos.gov.co", None, None, "USD")}
    assert {f.costo_unitario for f in filas} == {Decimal(str(cargar_tarifas()["datos.gov.co"]))}


def test_la_fuente_caida_en_un_lead_no_frena_al_resto(admin, tenants, cifrador, mundo):
    repo, costos, busqueda = mundo
    primero = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Caido Uno")
    segundo = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Transportes Andinos")
    transporte, _ = _rues({"CAIDO UNO": 503, "TRANSPORTES ANDINOS": [_fila("900111222", "TRANSPORTES ANDINOS SAS")]})

    r = _enriquecer(repo, costos, busqueda, transporte)

    assert (r.procesados, r.cortado, r.pendientes) == (2, False, 0)
    assert _lead(admin, primero)[:3] == ("desconocido", False, "persona_natural")
    assert _solicitudes(admin, primero)[0]["motivo"] == "fuente_no_disponible"
    assert _lead(admin, segundo)[:2] == ("juridica", True)


def test_el_nombre_del_lead_no_sale_en_los_logs(admin, tenants, cifrador, mundo, caplog):
    repo, costos, busqueda = mundo
    _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Zxqvk Ficticia Andina")
    _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Zxqvk Caida")
    transporte, _ = _rues({"ZXQVK FICTICIA ANDINA": [_fila("900111222", "ZXQVK FICTICIA ANDINA SAS")], "ZXQVK CAIDA": 500})
    caplog.set_level(logging.DEBUG)

    _enriquecer(repo, costos, busqueda, transporte)

    assert "ZXQVK" not in caplog.text.upper()


def test_lead_osm_con_telefono_que_matchea_queda_contactable_y_sale_en_el_export(cliente, admin, usuarios, cifrador, caplog):  # noqa: F811
    tenant = usuarios["tenant_a"]
    estado = cliente.app.state
    repo = RepositorioLeadsPostgres(estado.engine, tenant, estado.cifrador)
    busqueda = repo.crear_busqueda(CriteriosICP("CO", {}))
    si = _sembrar(repo, admin, estado.cifrador, tenant, busqueda, "Transportes Andinos")
    otra_ciudad = _sembrar(repo, admin, estado.cifrador, tenant, busqueda, "Carga Rapida")
    ambiguo = _sembrar(repo, admin, estado.cifrador, tenant, busqueda, "Fletes Dobles")
    estado.transporte_http, _ = _rues({
        "TRANSPORTES ANDINOS": [_fila("900111222", "TRANSPORTES ANDINOS S.A.S.")],
        "CARGA RAPIDA": [_fila("900555666", "CARGA RAPIDA SAS", camara="14")],
        "FLETES DOBLES": [_fila("900777888", "FLETES DOBLES SAS"), _fila("900999000", "FLETES DOBLES LTDA")]})
    caplog.set_level(logging.DEBUG)

    r = cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))

    assert r.status_code == 200 and (r.json()["procesados"], r.json()["contactables"]) == (3, 1)
    assert _lead(admin, si)[:3] == ("juridica", True, None)
    assert _lead(admin, otra_ciudad)[:2] == ("desconocido", False) and _lead(admin, ambiguo)[:2] == ("desconocido", False)
    export = cliente.get("/calificaciones/exportar", headers=_bearer(usuarios["a"]))
    filas = list(csv.DictReader(io.StringIO(export.text)))
    assert [(f["lead_id"], f["to_number"], f["first_name"]) for f in filas] == [(str(si), TELEFONO, "Transportes Andinos")]
    for texto in (r.text, caplog.text):
        assert "ANDINOS" not in texto.upper() and "CARGA RAPIDA" not in texto.upper()


def test_una_natural_homonima_deja_el_lead_desconocido_y_la_constancia_lo_dice(admin, tenants, cifrador, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, admin, cifrador, tenants["a"], busqueda, "Juan Pérez")
    transporte, _ = _rues({"JUAN PEREZ": [_fila("900111222", "JUAN PEREZ SAS")]}, naturales={"JUAN PEREZ": 1})

    _enriquecer(repo, costos, busqueda, transporte)

    assert _lead(admin, lead)[:3] == ("desconocido", False, "persona_natural")
    (entrada,) = _solicitudes(admin, lead)
    assert (entrada["motivo"], entrada["naturales_homonimas"]) == ("ambiguo", 1) and "nit" not in entrada
