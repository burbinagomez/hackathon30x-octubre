import os

import pytest
from sqlalchemy import create_engine

from app import db


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def rt():
    engine = db.crear_engine(_url("TEST_DATABASE_URL"))
    yield engine
    engine.dispose()


@pytest.fixture
def admin():
    engine = create_engine(_url("TEST_ADMIN_DATABASE_URL"))
    yield engine
    engine.dispose()
