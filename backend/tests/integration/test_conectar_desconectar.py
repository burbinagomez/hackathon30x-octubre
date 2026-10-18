import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import yaml
from sqlalchemy import text

from app import db
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.aplicacion.camaras import cargar_camaras
from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBusqueda
from app.modulos.descubrimiento.aplicacion.registro import (
    cargar_actividades,
    cargar_registro,
)
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import (
    RepositorioLeadsPostgres,
)

BACKEND = Path(__file__).resolve().parents[2]
CONFIG = BACKEND / "config"
FILAS = json.loads((BACKEND / "tests" / "fixtures" / "datos_gov_co" / "filas.json").read_text())
OSM = json.loads((BACKEND / "tests" / "fixtures" / "osm" / "bogota_4711.json").read_text())
ICP = CriteriosICP("CO", {"ciiu": "4711", "departamento": "11"})
HEADER_AS_OF = "Fri, 02 Oct 2026 21:39:26 GMT"
CLAVE = "datos_gov_co_rues"
INICIO = datetime(2026, 10, 17, tzinfo=UTC)


@pytest.fixture
def tenant(admin):
    a = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:a, 'A')"), {"a": a})
    yield a
    with admin.begin() as c:
        for t in ["lead_fuentes", "cumplimiento", "leads", "busquedas", "costos"]:
            c.execute(text(f"DELETE FROM {t} WHERE tenant_id = :a"), {"a": a})
        c.execute(text("DELETE FROM tenants WHERE id = :a"), {"a": a})


def _yaml(tmp_path, habilitado):
    """Copia del YAML real con datos_gov_co_rues en `habilitado` y, solo si está habilitada, las demás fuentes apagadas."""
    config = yaml.safe_load((CONFIG / "fuentes.yaml").read_text())
    fuentes = config["fuentes_descubrimiento"]
    for clave, entrada in fuentes.items():
        entrada["habilitado"] = habilitado if clave == CLAVE else False
    ruta = tmp_path / "fuentes.yaml"
    ruta.write_text(yaml.safe_dump(deepcopy(config), allow_unicode=True))
    return ruta


def _buscar(rt, tenant, ruta_yaml):
    """EjecutarBusqueda real: registro desde `ruta_yaml`, catálogo real, transporte falso por host y Postgres real."""
    registro = cargar_registro(ruta_yaml, catalogo)
    pedidas: list[httpx.Request] = []
    reloj = [0.0]

    def responder(request):
        pedidas.append(request)
        if request.url.host == "www.datos.gov.co":
            reloj[0] += 2.0
            return httpx.Response(200, json=FILAS, headers={"X-SODA2-Truth-Last-Modified": HEADER_AS_OF})
        return httpx.Response(200, json=OSM)

    def fabrica_de(clave, clase, meta):
        def armar(lote_id):
            costos = PostgresCostos(rt, tenant)
            transporte = httpx.MockTransport(responder)
            if clave == CLAVE:
                return clase(
                    transporte=transporte, reloj=lambda: INICIO + timedelta(seconds=reloj[0]), dormir=lambda _s: None,
                    costos=costos, cache=None, camaras=cargar_camaras(CONFIG / "camaras_co.yaml"),
                    tarifas={"computo_seg_usd": 0.0000070}, lote_id=lote_id, meta=meta,
                )
            return clase(meta=meta, registro_costos=costos, transporte=transporte, costo_unitario=0,
                         lote_id=lote_id, repo_url="https://example.invalid/repo")
        return armar

    fuentes = {c: (m, fabrica_de(c, k, m)) for c, (k, m) in registro.fuentes.items()}
    caso = EjecutarBusqueda(RepositorioLeadsPostgres(rt, tenant), fuentes, cargar_actividades(CONFIG / "actividades.yaml"))
    resultado = caso.ejecutar(ICP)
    return resultado, [r for r in pedidas if r.url.host == "www.datos.gov.co"]


def _ver(rt, tenant):
    with db.unidad_de_trabajo(rt, tenant) as c:
        leads = c.execute(text("SELECT id_fiscal, tipo_titular FROM leads")).all()
        licencias = c.execute(text("SELECT fuente, licencia, url_origen, as_of FROM cumplimiento")).all()
        lead_fuentes = c.execute(text("SELECT licencia FROM lead_fuentes")).all()
        costos = c.execute(text("SELECT tenant_id, tipo, proveedor, gratis FROM costos")).all()
    return leads, licencias, lead_fuentes, costos


def test_yaml_real_consulta_datos_gov_co(rt, tenant):
    _, a_datos_gov = _buscar(rt, tenant, CONFIG / "fuentes.yaml")

    assert len(a_datos_gov) >= 1


def test_habilitada_por_yaml_temporal_da_leads_cc_by_sa(rt, tenant, tmp_path):
    _buscar(rt, tenant, _yaml(tmp_path, habilitado=True))

    leads, cumplimiento, lead_fuentes, costos = _ver(rt, tenant)
    assert sorted(leads) == [(e["nit"], "juridica") for e in FILAS]
    assert {(f, lic, as_of.isoformat()) for f, lic, _, as_of in cumplimiento} == {
        (CLAVE, "CC-BY-SA-4.0", "2026-10-02T21:39:26+00:00")}
    assert {url for _, _, url, _ in cumplimiento} == {
        f"https://www.datos.gov.co/resource/c82u-588k.json?nit={e['nit']}" for e in FILAS}
    assert {lic for (lic,) in lead_fuentes} == {"CC-BY-SA-4.0"}
    assert costos == [(tenant, "socrata_descarga", "datos.gov.co", False)]


def test_deshabilitada_por_yaml_temporal_no_toca_datos_gov_co(rt, tenant, tmp_path):
    _, a_datos_gov = _buscar(rt, tenant, _yaml(tmp_path, habilitado=False))

    assert a_datos_gov == []
