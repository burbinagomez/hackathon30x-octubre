import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parents[2]


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def alembic():
    url = _url("TEST_MIGRATION_DATABASE_URL")

    def correr(*args, **env_extra):
        # MIGRATION_DATABASE_URL solo vive en el entorno del subproceso, nunca en el del test.
        env = {**os.environ, "MIGRATION_DATABASE_URL": url, **env_extra}
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True
        )

    return correr


@pytest.fixture
def admin():
    # app_mig no tiene CREATE en la base: el esquema ajeno lo crea un admin, solo en tests.
    with create_engine(_url("TEST_ADMIN_DATABASE_URL"), isolation_level="AUTOCOMMIT").connect() as c:
        yield c


def test_upgrade_head_desde_vacio(alembic):
    assert alembic("downgrade", "base").returncode == 0
    assert alembic("upgrade", "head").returncode == 0
    assert "(head)" in alembic("current").stdout
    assert alembic("check").returncode == 0


def test_drift_mira_solo_public_aunque_cambie_search_path(alembic, admin):
    pgoptions = "-c search_path=ajeno,public"
    admin.execute(text("DROP SCHEMA IF EXISTS ajeno CASCADE"))
    admin.execute(text("CREATE SCHEMA ajeno"))
    # Con USAGE y CREATE, sin el SET de env.py alembic_version caería en ajeno.
    admin.execute(text("GRANT USAGE, CREATE ON SCHEMA ajeno TO app_mig"))
    admin.execute(text("CREATE TABLE ajeno.t (id int)"))
    try:
        assert alembic("downgrade", "base", PGOPTIONS=pgoptions).returncode == 0
        assert alembic("upgrade", "head", PGOPTIONS=pgoptions).returncode == 0
        assert alembic("check", PGOPTIONS=pgoptions).returncode == 0
        assert admin.execute(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")).scalar()
        assert admin.execute(text("SELECT to_regclass('ajeno.alembic_version') IS NULL")).scalar()

        admin.execute(text("CREATE TABLE public.extra (id int)"))
        assert alembic("check", PGOPTIONS=pgoptions).returncode != 0
    finally:
        admin.execute(text("DROP TABLE IF EXISTS public.extra"))
        admin.execute(text("DROP SCHEMA ajeno CASCADE"))
