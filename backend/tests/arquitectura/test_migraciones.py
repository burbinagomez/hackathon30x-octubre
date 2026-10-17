import os
import subprocess
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, make_url, text

from app.modelos import metadata

BACKEND = Path(__file__).resolve().parents[2]
MIGRAR = BACKEND / "scripts" / "migrar_local.sh"
ROLES = BACKEND / "scripts" / "roles.sql"
BASE = "migraciones_t017"


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


def _migrar(url, migraciones=None):
    env = {**os.environ, **({"MIGRACIONES": str(migraciones)} if migraciones else {})}
    return subprocess.run(["bash", str(MIGRAR), url], env=env, capture_output=True, text=True)


def _drift(url, opciones=None):
    # Alembic solo como librería: compara la base con modelos.py, acotado a public.
    motor = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1),
                          connect_args={"options": opciones} if opciones else {})
    with motor.connect() as c:
        c.exec_driver_sql("SET search_path TO public, extensions")
        return compare_metadata(MigrationContext.configure(c), metadata)


@pytest.fixture
def admin():
    with create_engine(_url("TEST_ADMIN_DATABASE_URL"), isolation_level="AUTOCOMMIT").connect() as c:
        yield c


@pytest.fixture
def base_vacia(admin):
    # Base nueva por test: "desde vacío" de verdad, sin tocar la base que usan los demás tests.
    admin.execute(text(f"DROP DATABASE IF EXISTS {BASE} WITH (FORCE)"))
    admin.execute(text(f"CREATE DATABASE {BASE}"))
    url = make_url(_url("TEST_ADMIN_DATABASE_URL")).set(drivername="postgresql", database=BASE)
    url = url.render_as_string(hide_password=False)
    subprocess.run(["psql", url, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-f", str(ROLES)], check=True)
    yield url
    admin.execute(text(f"DROP DATABASE {BASE} WITH (FORCE)"))


def test_migrar_local_desde_vacio_dos_veces_sin_drift(base_vacia):
    assert _migrar(base_vacia).returncode == 0
    assert _migrar(base_vacia).returncode == 0
    assert _drift(base_vacia) == []


def test_migracion_aplicada_no_se_reaplica(base_vacia, tmp_path):
    # Sin IF NOT EXISTS: si el script la reaplicara, la segunda corrida fallaría.
    (tmp_path / "0001_t.sql").write_text("CREATE TABLE public.t (id int);")
    assert _migrar(base_vacia, tmp_path).returncode == 0
    segunda = _migrar(base_vacia, tmp_path)
    assert segunda.returncode == 0, segunda.stderr


def test_migracion_rota_falla_claro_y_no_deja_nada(base_vacia, tmp_path, admin):
    (tmp_path / "0001_rota.sql").write_text("CREATE TABLE public.u (id int);\nSELECT 1/0;")
    r = _migrar(base_vacia, tmp_path)
    assert r.returncode != 0
    assert "0001_rota.sql" in r.stderr
    with create_engine(base_vacia.replace("postgresql://", "postgresql+psycopg://", 1)).connect() as c:
        assert c.execute(text("SELECT to_regclass('public.u') IS NULL")).scalar()


def test_drift_mira_solo_public_aunque_cambie_search_path(base_vacia):
    assert _migrar(base_vacia).returncode == 0
    motor = create_engine(base_vacia.replace("postgresql://", "postgresql+psycopg://", 1),
                          isolation_level="AUTOCOMMIT")
    with motor.connect() as c:
        c.execute(text("CREATE SCHEMA ajeno"))
        c.execute(text("CREATE TABLE ajeno.t (id int)"))
        assert _drift(base_vacia, "-c search_path=ajeno,public") == []

        c.execute(text("CREATE TABLE public.extra (id int)"))
        assert _drift(base_vacia, "-c search_path=ajeno,public") != []
