import os

import pytest
from fastapi.testclient import TestClient

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
