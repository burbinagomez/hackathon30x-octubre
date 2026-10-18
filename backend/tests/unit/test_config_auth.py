"""AUTH_JWKS_URL y AUTH_ISSUER: URLs públicas de Supabase Auth; la api no guarda ningún secreto de firma."""
from app.config import Settings


def test_settings_lee_auth_jwks_url_y_auth_issuer(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app_rt@localhost/db")
    monkeypatch.setenv("CIFRADO_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://proyecto.example/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_ISSUER", "https://proyecto.example/auth/v1")

    s = Settings(_env_file=None)

    assert getattr(s, "auth_jwks_url", None) == "https://proyecto.example/auth/v1/.well-known/jwks.json"
    assert getattr(s, "auth_issuer", None) == "https://proyecto.example/auth/v1"
