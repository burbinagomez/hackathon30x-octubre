import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

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


TABLAS_DE_TENANT = ["lead_fuentes", "cumplimiento", "leads", "busquedas", "costos"]


@pytest.fixture
def tenants(admin):
    """Dos tenants, A y B, sembrados como postgres; al terminar se borra todo lo suyo."""
    ids = {"a": uuid4(), "b": uuid4()}
    with admin.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:a, 'A'), (:b, 'B')"), ids)
    yield ids
    with admin.begin() as c:
        for t in TABLAS_DE_TENANT:
            c.execute(text(f"DELETE FROM {t} WHERE tenant_id IN (:a, :b)"), ids)
        c.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), ids)
