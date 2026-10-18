"""scripts/crear_usuario.py: alta de la fila de usuarios (el usuario de Supabase lo crea el dueño en el panel)."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_RUTA = Path(__file__).resolve().parents[2] / "scripts" / "crear_usuario.py"
_spec = importlib.util.spec_from_file_location("crear_usuario", _RUTA)
crear_usuario = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crear_usuario)

MARCADOR = "marcador-de-password-7q2m"


def _fila(admin, auth_user_id):
    with admin.connect() as c:
        return c.execute(text("SELECT tenant_id, idioma FROM usuarios WHERE auth_user_id = :u"), {"u": auth_user_id}).all()


@pytest.mark.parametrize("idioma", ["en", None])
def test_crear_inserta_la_fila_del_usuario(admin, tenants, idioma):
    uid = uuid4()
    with admin.begin() as c:
        crear_usuario.crear(c, uid, tenants["a"], idioma)
    assert _fila(admin, uid) == [(tenants["a"], idioma)]


def test_crear_dos_veces_el_mismo_usuario_falla_y_no_lo_mueve_de_tenant(admin, tenants):
    uid = uuid4()
    with admin.begin() as c:
        crear_usuario.crear(c, uid, tenants["a"], "es")
    with pytest.raises(IntegrityError):
        with admin.begin() as c:
            crear_usuario.crear(c, uid, tenants["b"], "es")
    assert _fila(admin, uid) == [(tenants["a"], "es")]


def test_no_imprime_la_url_de_postgres(monkeypatch, capsys):
    url = f"postgresql://postgres:{MARCADOR}@127.0.0.1:1/postgres"  # puerto 1: conexión rechazada al toque
    monkeypatch.setattr(crear_usuario.getpass, "getpass", lambda *a, **k: url)
    codigo = crear_usuario.main(["--auth-user-id", str(uuid4()), "--tenant", str(uuid4())])
    salida = capsys.readouterr()
    assert codigo != 0
    assert "OperationalError" in salida.err  # falló por la conexión, no por un argumento
    assert MARCADOR not in salida.out + salida.err
