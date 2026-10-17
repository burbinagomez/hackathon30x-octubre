import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app import db

# fuente_cache queda fuera: es global, sin tenant_id. Guarda datos públicos de gobierno, no del tenant,
# y no se expone por API (spec, Decisiones técnicas).
EXCLUIDAS = {"fuente_cache"}
TABLAS = ["tenants", "busquedas", "leads", "lead_fuentes", "cumplimiento", "costos"]

PRIVILEGIO_INSUFICIENTE = "42501"  # también es el sqlstate de una violación de política RLS
FK_VIOLADA = "23503"


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
def datos():
    """Tenant A con una fila en cada tabla, y tenant B con una búsqueda y un lead propios. Sembrado como postgres."""
    a, b = uuid4(), uuid4()
    ids = {"tenants": a, "busquedas": uuid4(), "leads": uuid4(), "lead_fuentes": uuid4(),
           "cumplimiento": uuid4(), "costos": uuid4(), "lead_sin_cumplimiento": uuid4(),
           "busqueda_b": uuid4(), "lead_b": uuid4(), "a": a, "b": b}
    admin = create_engine(_url("TEST_ADMIN_DATABASE_URL"))
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:a, 'A'), (:b, 'B')"), ids)
            c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES "
                           "(:busquedas, :a, 'CO', '{}'), (:busqueda_b, :b, 'CO', '{}')"), ids)
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre) VALUES "
                           "(:leads, :a, 'CO', 'A1'), (:lead_sin_cumplimiento, :a, 'CO', 'A2'), "
                           "(:lead_b, :b, 'CO', 'B1')"), ids)
            c.execute(text("INSERT INTO lead_fuentes (id, tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                           "VALUES (:lead_fuentes, :a, :leads, :busquedas, 'f', 'u', 'l')"), ids)
            c.execute(text("INSERT INTO cumplimiento (id, tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
                           "VALUES (:cumplimiento, :a, :leads, 'f', 'l', 'u', now())"), ids)
            c.execute(text("INSERT INTO costos (id, tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, gratis) "
                           "VALUES (:costos, :a, 'croma_consulta', 1, 0, 'USD', 'croma', true)"), ids)
        yield ids
    finally:
        with admin.begin() as c:
            for t in ["lead_fuentes", "cumplimiento", "costos", "leads", "busquedas"]:
                c.execute(text(f"DELETE FROM {t} WHERE tenant_id IN (:a, :b)"), ids)
            c.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), ids)
        admin.dispose()


# INSERT de una fila nueva con el tenant_id de A. Usa el lead sin cumplimiento y otra fuente, para que
# ningún UNIQUE la rechace antes que la política.
INSERT_CON_TENANT_DE_A = {
    "tenants": "INSERT INTO tenants (nombre) VALUES ('intruso')",
    "busquedas": "INSERT INTO busquedas (tenant_id, pais, criterios) VALUES (:a, 'CO', '{}')",
    "leads": "INSERT INTO leads (tenant_id, pais, nombre) VALUES (:a, 'CO', 'intruso')",
    "lead_fuentes": "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                    "VALUES (:a, :lead_sin_cumplimiento, :busquedas, 'otra', 'u', 'l')",
    "cumplimiento": "INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
                    "VALUES (:a, :lead_sin_cumplimiento, 'f', 'l', 'u', now())",
    "costos": "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, gratis) "
              "VALUES (:a, 'croma_consulta', 1, 0, 'USD', 'croma', true)",
}


def _como_b(rt, datos, sql):
    with db.unidad_de_trabajo(rt, datos["b"]) as c:
        return c.execute(text(sql), datos)


def _rechazado(rt, datos, sql, sqlstate):
    with pytest.raises(DBAPIError) as exc:
        _como_b(rt, datos, sql)
    assert exc.value.orig.sqlstate == sqlstate


def test_la_lista_cubre_todas_las_tablas_de_public(rt):
    with rt.connect() as c:
        en_public = set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars())
    assert en_public == set(TABLAS) | EXCLUIDAS


@pytest.mark.parametrize("tabla", TABLAS)
def test_tenant_b_no_accede_a_datos_de_a(rt, datos, tabla):
    fila_de_a = f"WHERE id = '{datos[tabla]}'"
    assert _como_b(rt, datos, f"SELECT id FROM {tabla} {fila_de_a}").all() == []

    if tabla == "tenants":
        # app_rt solo tiene SELECT en tenants: la siembra corre con postgres.
        for sql in (f"UPDATE tenants SET nombre = nombre {fila_de_a}", f"DELETE FROM tenants {fila_de_a}"):
            _rechazado(rt, datos, sql, PRIVILEGIO_INSUFICIENTE)
    else:
        assert _como_b(rt, datos, f"UPDATE {tabla} SET id = id {fila_de_a}").rowcount == 0
        assert _como_b(rt, datos, f"DELETE FROM {tabla} {fila_de_a}").rowcount == 0

    _rechazado(rt, datos, INSERT_CON_TENANT_DE_A[tabla], PRIVILEGIO_INSUFICIENTE)


def test_tenant_b_no_muda_una_fila_propia_a_a(rt, datos):
    # WITH CHECK: B no puede dejar su búsqueda con el tenant_id de A. Sin WHERE a propósito: si el UPDATE
    # lee columnas, Postgres también aplica el USING a la fila nueva y el test no probaría el WITH CHECK.
    # RLS lo acota a las filas de B, y B tiene una sola búsqueda.
    _rechazado(rt, datos, "UPDATE busquedas SET tenant_id = :a", PRIVILEGIO_INSUFICIENTE)


# Con su propio tenant_id y un id de A (lead o búsqueda): la política lo deja pasar y una FK simple no pasa por RLS.
COLGAR_DE_LEAD_DE_A = {
    "lead_fuentes": "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                    "VALUES (:b, :lead_sin_cumplimiento, :busqueda_b, 'f', 'u', 'l')",
    "cumplimiento": "INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
                    "VALUES (:b, :lead_sin_cumplimiento, 'f', 'l', 'u', now())",
    "lead_fuentes_busqueda": "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                             "VALUES (:b, :lead_b, :busquedas, 'f', 'u', 'l')",
}


@pytest.mark.parametrize("tabla", sorted(COLGAR_DE_LEAD_DE_A))
def test_tenant_b_no_cuelga_filas_de_un_lead_de_a(rt, datos, tabla):
    _rechazado(rt, datos, COLGAR_DE_LEAD_DE_A[tabla], FK_VIOLADA)
