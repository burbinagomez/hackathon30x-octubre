import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import ProgrammingError

from app.config import SecretProhibido
from app.main import app


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def conn():
    with create_engine(_url("TEST_DATABASE_URL")).connect() as c:
        yield c


def test_rol_runtime_no_es_super_ni_bypassrls_ni_puede_crear(conn):
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


@pytest.mark.parametrize("atributo", ["SUPERUSER", "BYPASSRLS"])
def test_api_no_arranca_con_un_rol_que_saltea_rls(monkeypatch, atributo):
    # Sin "postgres" en el nombre: lo tiene que frenar la base, no el chequeo del string en config.py.
    admin = create_engine(_url("TEST_ADMIN_DATABASE_URL"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP ROLE IF EXISTS rt_peligroso"))
        c.execute(text(f"CREATE ROLE rt_peligroso LOGIN {atributo} PASSWORD 'peligroso-test'"))
    url = make_url(_url("TEST_DATABASE_URL")).set(username="rt_peligroso", password="peligroso-test")
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    try:
        with pytest.raises(SecretProhibido) as exc:
            with TestClient(app):
                pass
        assert "DATABASE_URL" in str(exc.value)
    finally:
        with admin.connect() as c:
            c.execute(text("DROP ROLE rt_peligroso"))
