import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app import db
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBusqueda
from app.modulos.descubrimiento.aplicacion.registro import cargar_actividades, cargar_registro
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres

BACKEND = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((BACKEND / "tests" / "fixtures" / "osm" / "bogota_4711.json").read_text())
TARIFA = Decimal("0.0000070")
ICP = CriteriosICP("CO", {"ciiu": "4711", "ciudad": "Bogotá"})


def _buscar(rt, tenant, cifrador):
    """EjecutarBusqueda real con el catálogo real, OSM con transporte falso (2 s por request) y Postgres real."""
    registro = cargar_registro(BACKEND / "config" / "fuentes.yaml", catalogo)
    clase, meta = registro.fuentes["osm_overpass"]
    ahora = [0.0]

    def responder(request):
        ahora[0] += 2.0
        return httpx.Response(200, json=FIXTURE)

    def fabrica(lote_id):
        return clase(meta=meta, registro_costos=PostgresCostos(rt, tenant), transporte=httpx.MockTransport(responder),
                     costo_unitario=TARIFA, lote_id=lote_id, repo_url="https://example.invalid/repo",
                     reloj=lambda: ahora[0])

    caso = EjecutarBusqueda(RepositorioLeadsPostgres(rt, tenant, cifrador), {"osm_overpass": (meta, fabrica)},
                            actividades=cargar_actividades(BACKEND / "config" / "actividades.yaml"))
    return caso.ejecutar(ICP)


def _ver(rt, tenant, cifrador):
    """Lo que el tenant ve a través de RLS: (leads, cumplimiento, costos)."""
    with db.unidad_de_trabajo(rt, tenant) as c:
        ids = c.execute(text("SELECT id FROM leads")).scalars().all()
        cumplimiento = c.execute(text("SELECT fuente, licencia, url_origen, as_of FROM cumplimiento")).all()
        costos = c.execute(text("SELECT tenant_id, tipo, unidades, costo_unitario, proveedor, fuente, lead_id, lote_id, gratis "
                                "FROM costos")).all()
    repo = RepositorioLeadsPostgres(rt, tenant, cifrador)  # el nombre solo se lee por el repositorio
    leads = [repo.obtener_lead(i) for i in ids]
    return leads, cumplimiento, costos


def test_osm_guarda_leads_en_el_tenant(rt, admin, tenants, cifrador):
    con_nombre = [el for el in FIXTURE["elements"] if el["tags"].get("name")]
    n = len(con_nombre)
    assert n > 0
    as_of = datetime.fromisoformat(FIXTURE["osm3s"]["timestamp_osm_base"])
    assert as_of.tzinfo is UTC

    resultado = _buscar(rt, tenants["a"], cifrador)

    leads_a, cumplimiento_a, costos_a = _ver(rt, tenants["a"], cifrador)
    assert len(leads_a) == n
    assert resultado.errores == {} and resultado.sin_fuente_para is None
    assert {(lead.nombre, lead.pais, lead.id_fiscal, lead.tipo_titular) for lead in leads_a} == {
        (el["tags"]["name"], "CO", None, "desconocido") for el in con_nombre}
    assert sorted(cumplimiento_a) == sorted(
        ("osm_overpass", "ODbL", f"https://www.openstreetmap.org/{el['type']}/{el['id']}", as_of) for el in con_nombre)
    assert costos_a == [(tenants["a"], "overpass_query", Decimal(2), TARIFA, "osm", "osm_overpass", None,
                         resultado.busqueda_id, False)]
    with admin.connect() as c:
        assert c.execute(text("SELECT count(*) FROM lead_fuentes WHERE tenant_id = :a AND busqueda_id = :b"),
                         {"a": tenants["a"], "b": resultado.busqueda_id}).scalar() == n

    # Aislamiento: B no ve nada de A, ni por RLS ni por tenant_id.
    assert _ver(rt, tenants["b"], cifrador) == ([], [], [])
    with admin.connect() as c:
        for tabla in ("leads", "cumplimiento", "costos", "busquedas", "lead_fuentes"):
            assert c.execute(text(f"SELECT count(*) FROM {tabla} WHERE tenant_id = :b"), {"b": tenants["b"]}).scalar() == 0
