import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, text

from app import db
from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.aplicacion.camaras import cargar_camaras
from app.modulos.descubrimiento.aplicacion.registro import cargar_registro
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente
from app.modulos.descubrimiento.infraestructura.adaptadores.datos_gov_co_rues import DatosGovCoRues
from app.modulos.descubrimiento.infraestructura.adaptadores.osm_overpass import OsmOverpass

PROVEEDOR = "croma"
BACKEND = Path(__file__).resolve().parents[2]
FIXTURE_OSM = BACKEND / "tests" / "fixtures" / "osm" / "bogota_4711.json"
FIXTURE_DATOS_GOV = BACKEND / "tests" / "fixtures" / "datos_gov_co" / "filas.json"


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def tenant(admin):
    a = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:a, 'A')"), {"a": a})
    yield a
    with admin.begin() as c:
        c.execute(text("DELETE FROM costos WHERE tenant_id = :a"), {"a": a})
        c.execute(text("DELETE FROM busquedas WHERE tenant_id = :a"), {"a": a})
        c.execute(text("DELETE FROM tenants WHERE id = :a"), {"a": a})


def _sembrar(admin, tenant, unidades, ts_sql, proveedor=PROVEEDOR):
    """Fila de costos con ts calculado por la base (ts_sql es una expresión SQL fija del test)."""
    with admin.begin() as c:
        c.execute(text("INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, gratis, ts) "
                       f"VALUES (:t, 'croma_consulta', :u, 0.00099, 'USD', :p, true, {ts_sql})"),
                  {"t": tenant, "u": unidades, "p": proveedor})


INICIO_MES_UTC = "(date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')"


def test_requests_24h_cuenta_filas_en_ventana(rt, admin, tenant):
    _sembrar(admin, tenant, 0, "now() - interval '23 hours 59 minutes'")  # un 502: cuenta como request
    _sembrar(admin, tenant, 10, "now() - interval '24 hours 1 minute'")
    _sembrar(admin, tenant, 1, "now() - interval '1 hour'", proveedor="osm")  # otro proveedor: no cuenta
    assert PostgresCostos(rt, tenant).requests_24h(PROVEEDOR) == 1


def test_creditos_mes_suma_unidades_del_mes_calendario_utc(admin, tenant):
    _sembrar(admin, tenant, 10, f"{INICIO_MES_UTC} - interval '1 minute'")
    _sembrar(admin, tenant, 1, f"{INICIO_MES_UTC} + interval '1 minute'")
    _sembrar(admin, tenant, 10, f"{INICIO_MES_UTC} + interval '1 minute'")
    _sembrar(admin, tenant, 5, f"{INICIO_MES_UTC} + interval '1 minute'", proveedor="osm")  # otro proveedor: no suma
    engine = db.crear_engine(_url("TEST_DATABASE_URL"))

    @event.listens_for(engine, "connect")
    def _zona_bogota(conexion_dbapi, _registro):
        with conexion_dbapi.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'America/Bogota'")  # UTC-5: con la zona de sesión el mes arranca 05:00 UTC y quedan afuera las de 00:01
        conexion_dbapi.commit()

    try:
        with engine.connect() as c:
            assert c.execute(text("SHOW TIME ZONE")).scalar() == "America/Bogota"
        assert PostgresCostos(engine, tenant).creditos_mes(PROVEEDOR) == Decimal(11)
    finally:
        engine.dispose()


def test_registrar_sobrevive_al_rollback_de_otra_transaccion(rt, admin, tenant):
    lote, lead = uuid4(), uuid4()  # costos.lead_id no tiene FK
    op = OperacionCosto(tipo="overpass_query", unidades=Decimal(1), costo_unitario=Decimal(0), moneda="USD",
                        proveedor="osm", fuente="osm", canal=None, lead_id=lead, lote_id=lote, gratis=True)
    with pytest.raises(RuntimeError):
        with db.unidad_de_trabajo(rt, tenant) as c:
            c.execute(text("INSERT INTO busquedas (tenant_id, pais, criterios) VALUES (:t, 'CO', '{}')"), {"t": tenant})
            PostgresCostos(rt, tenant).registrar(op)
            raise RuntimeError("falla lo que viene después")
    with admin.connect() as c:
        costos = c.execute(text("SELECT tipo, unidades, costo_unitario, moneda, proveedor, fuente, canal, lead_id, lote_id, "
                                "gratis FROM costos WHERE tenant_id = :t"), {"t": tenant}).all()
        busquedas = c.execute(text("SELECT count(*) FROM busquedas WHERE tenant_id = :t"), {"t": tenant}).scalar()
    assert costos == [("overpass_query", Decimal(1), Decimal(0), "USD", "osm", "osm", None, lead, lote, True)]
    assert busquedas == 0


def test_overpass_query_escribe_fila_en_costos(rt, admin, tenant):
    """OSM real contra el libro real: 1 request deja 1 fila `overpass_query` del tenant, con la tarifa como numeric."""
    meta = cargar_registro(BACKEND / "config" / "fuentes.yaml", {"osm_overpass": object}).fuentes["osm_overpass"][1]
    ahora = [100.0]

    def responder(request):
        ahora[0] += 2.0  # el request "dura" 2 s
        return httpx.Response(200, json=json.loads(FIXTURE_OSM.read_text()))

    lote = uuid4()
    adaptador = OsmOverpass(meta=meta, registro_costos=PostgresCostos(rt, tenant), transporte=httpx.MockTransport(responder),
                            costo_unitario=Decimal("0.0000070"), lote_id=lote, repo_url="https://example.invalid/repo",
                            reloj=lambda: ahora[0])

    adaptador.buscar(CriteriosICP("CO", {"ciudad": "Bogotá", "tipo_negocio": ("shop=supermarket",)}), 1)

    with admin.connect() as c:
        filas = c.execute(text("SELECT tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, lead_id, "
                               "lote_id, gratis FROM costos WHERE tenant_id = :t"), {"t": tenant}).all()
        tipo_costo = c.execute(text("SELECT data_type FROM information_schema.columns "
                                    "WHERE table_schema = 'public' AND table_name = 'costos' AND column_name = 'costo_unitario'")).scalar()
    assert filas == [(tenant, "overpass_query", Decimal(2), Decimal("0.0000070"), "USD", "osm", "osm_overpass", None, lote, False)]
    assert tipo_costo == "numeric"


def test_socrata_descarga_escribe_fila_en_costos(rt, admin, tenant):
    """datos.gov.co real contra el libro real: 1 request deja 1 fila `socrata_descarga` del tenant (rol app_rt)."""
    inicio = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    reloj = [inicio]

    def responder(request):
        reloj[0] += timedelta(seconds=2)  # el request "dura" 2 s
        return httpx.Response(200, json=json.loads(FIXTURE_DATOS_GOV.read_text()))

    meta = MetaFuente(clave="datos_gov_co_rues", proveedor="datos.gov.co", paises=frozenset({"CO"}),
                      filtros=frozenset({"ciiu", "departamento"}), trae=frozenset({"nit", "nombre", "ciiu", "ciudad_camara"}),
                      tipo="dataset", licencia="CC-BY-SA-4.0")
    lote = uuid4()
    adaptador = DatosGovCoRues(transporte=httpx.MockTransport(responder), reloj=lambda: reloj[0],
                               monotonico=lambda: (reloj[0] - inicio).total_seconds(), dormir=lambda _s: None,
                               costos=PostgresCostos(rt, tenant), cache=None,
                               camaras=cargar_camaras(BACKEND / "config" / "camaras_co.yaml"),
                               tarifas={"computo_seg_usd": 0.0000070}, lote_id=lote, meta=meta)

    adaptador.buscar(CriteriosICP("CO", {"ciiu": "4711", "departamento": "11"}), 1)

    with admin.connect() as c:
        filas = c.execute(text("SELECT tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, lead_id, "
                               "lote_id, gratis FROM costos WHERE tenant_id = :t"), {"t": tenant}).all()
        tipo_costo = c.execute(text("SELECT data_type FROM information_schema.columns "
                                    "WHERE table_schema = 'public' AND table_name = 'costos' AND column_name = 'costo_unitario'")).scalar()
    assert filas == [(tenant, "socrata_descarga", Decimal(2), Decimal("0.0000070"), "USD", "datos.gov.co",
                      "datos_gov_co_rues", None, lote, False)]
    assert tipo_costo == "numeric"


def _fila_de_lote(admin, tenant, lote, unidades, costo_unitario, gratis):
    with admin.begin() as c:
        c.execute(text("INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, gratis, lote_id) "
                       "VALUES (:t, 'croma_consulta', :u, :cu, 'USD', 'croma', :g, :l)"),
                  {"t": tenant, "u": Decimal(unidades), "cu": Decimal(costo_unitario), "g": gratis, "l": lote})


def test_gasto_busqueda_suma_lista_del_lote(rt, admin, tenant):
    lote, otro = uuid4(), uuid4()
    _fila_de_lote(admin, tenant, lote, "1", "0.40", True)  # gratis: el tope cuenta el valor de lista
    _fila_de_lote(admin, tenant, lote, "3", "0.0235", False)
    _fila_de_lote(admin, tenant, otro, "1", "9.99", False)  # otro lote: no entra

    gasto = PostgresCostos(rt, tenant).gasto_busqueda(lote)

    assert type(gasto) is Decimal
    assert gasto == Decimal("0.4705")


def test_gasto_busqueda_sin_filas_es_cero(rt, tenant):
    gasto = PostgresCostos(rt, tenant).gasto_busqueda(uuid4())

    assert type(gasto) is Decimal
    assert gasto == Decimal("0")
