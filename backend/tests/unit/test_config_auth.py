"""AUTH_JWKS_URL y AUTH_ISSUER: URLs públicas de Supabase Auth; la api no guarda ningún secreto de firma."""
import pytest
from pydantic import ValidationError

from app.config import SettingsApi


def test_settings_lee_auth_jwks_url_y_auth_issuer(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app_rt@localhost/db")
    monkeypatch.setenv("CIFRADO_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://proyecto.example/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_ISSUER", "https://proyecto.example/auth/v1")

    s = SettingsApi(_env_file=None)

    assert getattr(s, "auth_jwks_url", None) == "https://proyecto.example/auth/v1/.well-known/jwks.json"
    assert getattr(s, "auth_issuer", None) == "https://proyecto.example/auth/v1"


def _base(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app_rt@localhost/db")
    monkeypatch.setenv("CIFRADO_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://proyecto.example/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_ISSUER", "https://proyecto.example/auth/v1")


def test_baja_secret_vacia_es_none_y_la_api_arranca(monkeypatch):
    """El compose local pasa BAJA_SECRET="" si no está en el .env: la api arranca y /baja responde 404."""
    _base(monkeypatch)
    monkeypatch.setenv("BAJA_SECRET", "")
    assert SettingsApi(_env_file=None).baja_secret is None


def test_baja_secret_corta_sigue_rechazada(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setenv("BAJA_SECRET", "corta")
    with pytest.raises(ValidationError):
        SettingsApi(_env_file=None)
