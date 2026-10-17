import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import ProgrammingError

from app import db
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


@pytest.fixture(params=["SUPERUSER", "BYPASSRLS"])
def url_peligrosa(request):
    # Sin "postgres" en el nombre: lo tiene que frenar la base, no el chequeo del string en config.py.
    admin = create_engine(_url("TEST_ADMIN_DATABASE_URL"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP ROLE IF EXISTS rt_peligroso"))
        c.execute(text(f"CREATE ROLE rt_peligroso LOGIN {request.param} PASSWORD 'peligroso-test'"))
    url = make_url(_url("TEST_DATABASE_URL")).set(username="rt_peligroso", password="peligroso-test")
    yield url.render_as_string(hide_password=False)
    with admin.connect() as c:
        c.execute(text("DROP ROLE rt_peligroso"))


def test_api_no_arranca_con_un_rol_que_saltea_rls(monkeypatch, url_peligrosa):
    monkeypatch.setenv("DATABASE_URL", url_peligrosa)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    with pytest.raises(SecretProhibido) as exc:
        with TestClient(app):
            pass
    assert "DATABASE_URL" in str(exc.value)


def test_la_primera_conexion_real_chequea_el_rol_aunque_el_arranque_no_haya_podido(url_peligrosa):
    # Base caída al arrancar = el engine existe pero nunca conectó; el chequeo tiene que correr igual al conectar.
    engine = db.crear_engine(url_peligrosa)
    for _ in range(2):  # y no se "gasta" al fallar: la segunda conexión también se frena
        with pytest.raises(SecretProhibido):
            engine.connect().close()
