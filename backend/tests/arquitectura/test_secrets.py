import base64
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

DOCKERFILE_WEB = Path(__file__).resolve().parents[3] / "frontend" / "Dockerfile"


def _jwt(payload: dict) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'HS256', 'typ': 'JWT'})}.{seg(payload)}.firma"


@pytest.fixture
def entorno(monkeypatch):
    for k in list(os.environ):
        monkeypatch.delenv(k)
    monkeypatch.setenv("DATABASE_URL", "postgresql://app_rt:x@localhost/db")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    return monkeypatch


def _arrancar():
    with TestClient(app):
        pass


@pytest.mark.parametrize("nombre, valor", [
    ("MIGRATION_DATABASE_URL", "postgresql://app_mig:valor-secreto-1@host/db"),
    ("SUPABASE_SERVICE_ROLE_KEY", "valor-secreto-2"),
    ("API_KEY", "sb_publishable_valorsecreto3"),
    ("OTRA_KEY", "sb_secret_valorsecreto4"),
    ("ANON_TOKEN", _jwt({"role": "anon"})),
    ("ADMIN_TOKEN", _jwt({"role": "service_role"})),
])
def test_app_no_arranca_con_secret_prohibido(entorno, caplog, capsys, nombre, valor):
    entorno.setenv(nombre, valor)

    with pytest.raises(Exception) as exc:
        _arrancar()

    assert nombre in str(exc.value)
    salida = capsys.readouterr()
    for texto in (str(exc.value), caplog.text, salida.out, salida.err):
        assert valor not in texto


def test_jwt_malformado_no_filtra_el_valor(entorno, caplog, capsys):
    valor = "eyJhbGciOi.no-es-base64!.firma"
    entorno.setenv("FOO_TOKEN", valor)
    _arrancar()

    entorno.setenv("SUPABASE_X", valor)
    with pytest.raises(Exception) as exc:
        _arrancar()

    assert "SUPABASE_X" in str(exc.value)
    salida = capsys.readouterr()
    for texto in (str(exc.value), caplog.text, salida.out, salida.err):
        assert valor not in texto


def test_app_arranca_con_entorno_limpio(entorno):
    _arrancar()


def test_dockerfile_web_solo_recibe_vite_api_url():
    # Railway solo pasa al build lo declarado como ARG: lo único que puede llegar al bundle.
    lineas = DOCKERFILE_WEB.read_text().splitlines()
    args = {l.split()[1].split("=")[0] for l in lineas if l.strip().upper().startswith("ARG ")}
    assert args == {"VITE_API_URL"}
