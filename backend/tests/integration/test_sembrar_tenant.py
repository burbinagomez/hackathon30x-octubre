import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

_RUTA = Path(__file__).resolve().parents[2] / "scripts" / "sembrar_tenant.py"
_spec = importlib.util.spec_from_file_location("sembrar_tenant", _RUTA)
sembrar_tenant = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sembrar_tenant)

MARCADOR = "marcador-de-password-9f3k"


@pytest.fixture
def admin():
    url = os.environ.get("TEST_ADMIN_DATABASE_URL")
    if not url:
        pytest.fail("falta TEST_ADMIN_DATABASE_URL: los tests de integración fallan, no se saltan (R6)")
    engine = create_engine(url)
    yield engine
    engine.dispose()


def test_sembrar_dos_veces_mismo_id_actualiza(admin):
    tenant_id = uuid4()
    try:
        with admin.begin() as c:
            sembrar_tenant.sembrar(c, tenant_id, "Evento", "es")
        with admin.begin() as c:
            sembrar_tenant.sembrar(c, tenant_id, "Evento 30X", "en")
        with admin.connect() as c:
            filas = c.execute(text("SELECT nombre, idioma FROM tenants WHERE id = :id"), {"id": tenant_id}).all()
        assert filas == [("Evento 30X", "en")]
    finally:
        with admin.begin() as c:
            c.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


def test_no_imprime_la_url_de_postgres(monkeypatch, capsys):
    url = f"postgresql://postgres:{MARCADOR}@127.0.0.1:1/postgres"  # puerto 1: conexión rechazada al toque
    monkeypatch.setattr(sembrar_tenant.getpass, "getpass", lambda *a, **k: url)
    codigo = sembrar_tenant.main(["--nombre", "Evento"])
    salida = capsys.readouterr()
    assert codigo != 0
    assert MARCADOR not in salida.out + salida.err
