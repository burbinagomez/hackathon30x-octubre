import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app import db


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


TENANT = "SELECT current_setting('app.tenant_id', true)"
PID = "SELECT pg_backend_pid()"


def test_tenant_no_sobrevive_al_commit():
    # Engine nuevo: el pool tiene una sola conexión ociosa y se reusa; el pid prueba que es la misma física.
    engine = db.crear_engine(_url("TEST_DATABASE_URL"))
    tenant = uuid4()
    try:
        with db.unidad_de_trabajo(engine, tenant) as c:
            pid = c.execute(text(PID)).scalar()
            assert c.execute(text(TENANT)).scalar() == str(tenant)
        with engine.connect() as c:
            assert c.execute(text(PID)).scalar() == pid
            assert c.execute(text(TENANT)).scalar() in ("", None)
    finally:
        engine.dispose()


ROLES_SUPABASE = ["anon", "authenticated"]
PRIVILEGIOS = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]


PRIVILEGIOS_DE_COLUMNA = ["SELECT", "INSERT", "UPDATE"]


def _concedidos(c, rol, tablas):
    # has_table_privilege no ve un GRANT por columna: has_any_column_privilege sí.
    de_tabla = [(t, p) for t in tablas for p in PRIVILEGIOS
                if c.execute(text("SELECT has_table_privilege(:rol, :t, :p)"),
                             {"rol": rol, "t": f"public.{t}", "p": p}).scalar()]
    de_columna = [(t, f"{p} (columna)") for t in tablas for p in PRIVILEGIOS_DE_COLUMNA
                  if c.execute(text("SELECT has_any_column_privilege(:rol, :t, :p)"),
                               {"rol": rol, "t": f"public.{t}", "p": p}).scalar()]
    return de_tabla + [x for x in de_columna if x[0] not in {t for t, _ in de_tabla}]


@pytest.fixture
def admin():
    engine = create_engine(_url("TEST_ADMIN_DATABASE_URL"))
    try:
        with engine.connect() as c:
            yield c
    finally:
        engine.dispose()


# ponytail: un caso por rol y no por rol-tabla; la lista sale de pg_tables en runtime y el assert nombra
# cada (tabla, privilegio) concedido. Parametrizar por tabla exigiría consultar la base al colectar.
@pytest.mark.parametrize("rol", ROLES_SUPABASE)
def test_anon_y_authenticated_sin_privilegios(admin, rol):
    tablas = list(admin.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                                     "UNION SELECT viewname FROM pg_views WHERE schemaname = 'public'")).scalars())
    assert "leads" in tablas  # una lista vacía dejaría el test verde sin probar nada
    assert "v_tablero_fuentes" in tablas  # y sin las vistas el test no vería un GRANT a anon sobre ellas
    assert {"calificaciones", "v_cpql"} <= set(tablas)  # 008: la tabla y la vista nuevas entran al barrido
    assert _concedidos(admin, rol, tablas) == []


def test_default_privileges_no_conceden_a_anon_ni_authenticated(admin):
    # Tabla regular, no TEMP: una TEMP va a pg_temp y no le aplican los defaults de public.
    transaccion = admin.begin()
    try:
        admin.execute(text("CREATE TABLE public.x (id int)"))
        assert {rol: _concedidos(admin, rol, ["x"]) for rol in ROLES_SUPABASE} == {"anon": [], "authenticated": []}
    finally:
        transaccion.rollback()


def test_default_privileges_no_dan_execute_en_funciones_nuevas(admin):
    # Gemelo del de tablas: una función nueva de postgres no hereda EXECUTE de PUBLIC (default global de Postgres)
    # ni de los default privileges de Supabase para anon/authenticated. "public" es el pseudo-rol PUBLIC.
    transaccion = admin.begin()
    try:
        admin.execute(text("CREATE FUNCTION public.x() RETURNS int LANGUAGE sql AS 'SELECT 1'"))
        permisos = {rol: admin.execute(text("SELECT has_function_privilege(:rol, 'public.x()', 'EXECUTE')"),
                                       {"rol": rol}).scalar() for rol in (*ROLES_SUPABASE, "public")}
    finally:
        transaccion.rollback()
    assert permisos == {"anon": False, "authenticated": False, "public": False}


def test_anon_y_authenticated_sin_execute_en_funciones_de_public(admin):
    # Supabase da EXECUTE en funciones nuevas a anon/authenticated (default privileges) y Postgres a PUBLIC:
    # cualquier función de public tiene que cerrarse a mano. Las de extensiones (pg_trgm) viven en extensions.
    funciones = list(admin.execute(text(
        "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.prokind = 'f' "
        "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')")).scalars())
    assert any(f.startswith("tenant_de_usuario") for f in funciones)  # una lista vacía dejaría el test verde sin probar nada
    abiertas = [(f, rol) for f in funciones for rol in ROLES_SUPABASE
                if admin.execute(text("SELECT has_function_privilege(:rol, :f, 'EXECUTE')"), {"rol": rol, "f": f}).scalar()]
    assert abiertas == []
