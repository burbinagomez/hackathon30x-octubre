import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import db


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


TENANT = "SELECT current_setting('app.tenant_id', true)"
PID = "SELECT pg_backend_pid()"


def test_tenant_no_sobrevive_al_commit():
    # Engine nuevo: el pool tiene una sola conexión ociosa y se reusa; el pid prueba que es la misma física.
    engine = db.crear_engine(_url("TEST_DATABASE_URL"))
    tenant = uuid4()
    try:
        with db.unidad_de_trabajo(engine, tenant) as c:
            pid = c.execute(text(PID)).scalar()
            assert c.execute(text(TENANT)).scalar() == str(tenant)
        with engine.connect() as c:
            assert c.execute(text(PID)).scalar() == pid
            assert c.execute(text(TENANT)).scalar() in ("", None)
    finally:
        engine.dispose()
