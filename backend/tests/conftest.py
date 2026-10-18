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
def _cifrado_key_de_test(monkeypatch):
    # La app no arranca sin CIFRADO_KEY; los tests que la necesitan ausente la quitan con delenv.
    monkeypatch.setenv("CIFRADO_KEY", nueva_clave_de_cifrado())


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def rt_engine():
    """Engine como app_rt (RLS aplica)."""
    from app import db

    engine = db.crear_engine(_url("TEST_DATABASE_URL"))
    yield engine
    engine.dispose()


@pytest.fixture
def admin_engine():
    """Engine como postgres: solo para sembrar y limpiar."""
    from sqlalchemy import create_engine

    engine = create_engine(_url("TEST_ADMIN_DATABASE_URL"))
    yield engine
    engine.dispose()
