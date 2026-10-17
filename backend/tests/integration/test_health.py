import importlib
import os
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as modulo_main
from app.main import app


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _url("TEST_DATABASE_URL"))
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    return monkeypatch


def test_health_consulta_db(entorno):
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_health_db_caida(entorno):
    # Puerto sin nada escuchando: falla rápido por conexión rechazada, sin timeout largo.
    entorno.setenv("DATABASE_URL", "postgresql+psycopg://app_rt@localhost:1/postgres")
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "error", "db": "error"}


class _EngineFalso:
    @contextmanager
    def connect(self):
        yield SimpleNamespace(execute=lambda *a, **k: None)


def test_health_lee_el_engine_de_su_propia_app_tras_un_reload():
    # test_cors recarga app.main: el `app` importado acá queda viejo y no es el global del módulo.
    importlib.reload(modulo_main)
    app.state.engine = _EngineFalso()
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}
