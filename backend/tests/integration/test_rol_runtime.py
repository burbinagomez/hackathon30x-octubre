import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError


@pytest.fixture
def conn():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("falta TEST_DATABASE_URL: los tests de integración fallan, no se saltan (R6)")
    with create_engine(url).connect() as c:
        yield c


def test_rol_runtime_no_es_super_ni_bypassrls_ni_puede_crear(conn):
    # Cubre el hueco de que alguien ponga la URL del owner en DATABASE_URL.
    atributos = conn.execute(text(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = current_user"
    )).one()
    assert tuple(atributos) == (False, False, False, False)

    propios = conn.execute(text(
        "SELECT (SELECT count(*) FROM pg_namespace WHERE nspowner = r.oid)"
        "     + (SELECT count(*) FROM pg_class WHERE relowner = r.oid)"
        " FROM pg_roles r WHERE r.rolname = current_user"
    )).scalar()
    assert propios == 0

    with pytest.raises(ProgrammingError) as exc:
        conn.execute(text("CREATE TABLE public.x ()"))
    assert exc.value.orig.sqlstate == "42501"  # insufficient_privilege
    conn.rollback()

    assert conn.execute(text("SELECT has_schema_privilege(current_user, 'extensions', 'USAGE')")).scalar()
