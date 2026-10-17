import importlib

import pytest
from fastapi.testclient import TestClient

import app.main


@pytest.fixture
def app_con_origenes(monkeypatch):
    # El middleware CORS se arma al importar app.main: hay que recargarlo después del setenv.
    monkeypatch.setenv("CORS_ORIGINS", "https://web.example/, https://otro.example")
    yield importlib.reload(app.main).app
    monkeypatch.undo()
    importlib.reload(app.main)


@pytest.mark.parametrize("origen", ["https://web.example", "https://otro.example"])
def test_cors_normaliza_espacios_y_barra_final(app_con_origenes, origen):
    # Sin `with`: no corre el lifespan, no hace falta DB. El header CORS sale igual (aunque /health dé 503).
    r = TestClient(app_con_origenes).get("/health", headers={"Origin": origen})
    assert r.headers.get("access-control-allow-origin") == origen
