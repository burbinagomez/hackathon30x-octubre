import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text

from app import db
from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos

PROVEEDOR = "croma"


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def rt():
    engine = db.crear_engine(_url("TEST_DATABASE_URL"))
    yield engine
    engine.dispose()


@pytest.fixture
def admin():
    engine = create_engine(_url("TEST_ADMIN_DATABASE_URL"))
    yield engine
    engine.dispose()


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
