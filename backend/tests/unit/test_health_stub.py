from fastapi.testclient import TestClient

from app.main import app


def test_health_responde_200():
    assert TestClient(app).get("/health").status_code == 200
