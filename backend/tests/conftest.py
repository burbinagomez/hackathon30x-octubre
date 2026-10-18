import base64
import os

import pytest


def nueva_clave_de_cifrado() -> str:
    """Una clave de 32 bytes en base64, distinta en cada corrida. Nunca una real."""
    return base64.b64encode(os.urandom(32)).decode()


@pytest.fixture
def clave_cifrado() -> str:
    return nueva_clave_de_cifrado()


@pytest.fixture
def cifrador(clave_cifrado):
    from app.seguridad.cifrado import Cifrador

    return Cifrador(clave_cifrado)


@pytest.fixture(autouse=True)
def _auth_de_test(monkeypatch):
    # AUTH_* son obligatorias (URLs públicas, no secretos); los tests que las necesitan ausentes las quitan con delenv.
    monkeypatch.setenv("AUTH_JWKS_URL", "https://proyecto.example/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_ISSUER", "https://proyecto.example/auth/v1")


@pytest.fixture(autouse=True)
def _cifrado_key_de_test(monkeypatch):
    # La app no arranca sin CIFRADO_KEY; los tests que la necesitan ausente la quitan con delenv.
    monkeypatch.setenv("CIFRADO_KEY", nueva_clave_de_cifrado())
