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
    assert _aplicadas(base_vacia) == "0001"


def _consultar(url, sql):
    with create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1)).connect() as c:
        return c.execute(text(sql)).scalar()


def _aplicadas(url):
    return _consultar(url, "SELECT string_agg(version, ',' ORDER BY version) "
                           "FROM supabase_migrations.schema_migrations")


def test_aplica_solo_lo_que_falta_y_en_orden(base_vacia, tmp_path):
    # Sin IF NOT EXISTS: si el script reaplicara 0001, la segunda corrida fallaría.
    (tmp_path / "0001_t.sql").write_text("CREATE TABLE public.t (id int);")
    assert _migrar(base_vacia, tmp_path).returncode == 0
    assert _consultar(base_vacia, "SELECT to_regclass('public.t') IS NOT NULL")
    assert _aplicadas(base_vacia) == "0001"

    (tmp_path / "0002_y.sql").write_text("ALTER TABLE public.t ADD COLUMN y int;")
    segunda = _migrar(base_vacia, tmp_path)
    assert segunda.returncode == 0, segunda.stderr
    assert _aplicadas(base_vacia) == "0001,0002"


def test_aplica_varias_pendientes_en_orden_en_una_corrida(base_vacia, tmp_path):
    # 0002 depende de 0001: si se aplicaran fuera de orden, la corrida fallaría.
    (tmp_path / "0001_t.sql").write_text("CREATE TABLE public.t (id int);")
    (tmp_path / "0002_y.sql").write_text("ALTER TABLE public.t ADD COLUMN y int;")
    r = _migrar(base_vacia, tmp_path)
    assert r.returncode == 0, r.stderr
    assert _aplicadas(base_vacia) == "0001,0002"


def test_migracion_rota_falla_claro_y_no_deja_nada(base_vacia, tmp_path, admin):
    (tmp_path / "0001_rota.sql").write_text("CREATE TABLE public.u (id int);\nSELECT 1/0;")
    r = _migrar(base_vacia, tmp_path)
    assert r.returncode != 0
    assert "0001_rota.sql" in r.stderr
    assert _consultar(base_vacia, "SELECT to_regclass('public.u') IS NULL")
    # Si quedara la fila, la corrida siguiente saltearía el archivo roto y daría verde.
    assert _aplicadas(base_vacia) is None


def test_version_repetida_falla_y_nombra_los_dos(base_vacia, tmp_path):
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "0001_b.sql").write_text("SELECT 1;")
    r = _migrar(base_vacia, tmp_path)
    assert r.returncode != 0
    assert "0001_a.sql" in r.stderr and "0001_b.sql" in r.stderr


def test_nombre_invalido_falla(base_vacia, tmp_path):
    # El patrón es lo que vuelve seguro interpolar version y name en el INSERT.
    (tmp_path / "0001_Mal'.sql").write_text("SELECT 1;")
    r = _migrar(base_vacia, tmp_path)
    assert r.returncode != 0
    assert "nombre inválido" in r.stderr


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
