"""usuarios: app_rt no la toca; entra solo por tenant_de_usuario (SECURITY DEFINER)."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import db

PRIVILEGIO_INSUFICIENTE = "42501"


@pytest.fixture
def usuarios(admin, tenants):
    """Un usuario en A (idioma 'en') y uno en B (sin elección), sembrados como postgres. tenants limpia las filas."""
    ids = {"a": uuid4(), "b": uuid4(), "tenant_a": tenants["a"], "tenant_b": tenants["b"]}
    with admin.begin() as c:
        c.execute(text("INSERT INTO usuarios (auth_user_id, tenant_id, idioma) VALUES "
                       "(:a, :tenant_a, 'en'), (:b, :tenant_b, NULL)"), ids)
    return ids


@pytest.mark.parametrize("sql", [
    "SELECT * FROM usuarios",
    "INSERT INTO usuarios (auth_user_id, tenant_id) VALUES (gen_random_uuid(), :tenant_a)",
    "UPDATE usuarios SET idioma = 'es'",
    "DELETE FROM usuarios",
])
def test_app_rt_no_lee_usuarios_directo(rt, usuarios, sql):
    # Con el tenant de la fila fijado: el 42501 es de privilegios, no de un current_setting que falta.
    with pytest.raises(DBAPIError) as exc:
        with db.unidad_de_trabajo(rt, usuarios["tenant_a"]) as c:
            c.execute(text(sql), usuarios)
    assert exc.value.orig.sqlstate == PRIVILEGIO_INSUFICIENTE


def _tenant_de_usuario(rt, auth_user_id):
    # Sin app.tenant_id: el login ocurre antes de conocer el tenant.
    with rt.connect() as c:
        return c.execute(text("SELECT tenant_id, idioma_usuario, idioma_tenant FROM tenant_de_usuario(:uid)"),
                         {"uid": auth_user_id}).all()


def test_tenant_de_usuario_devuelve_solo_ese_usuario(rt, usuarios):
    assert _tenant_de_usuario(rt, usuarios["a"]) == [(usuarios["tenant_a"], "en", "es")]
    assert _tenant_de_usuario(rt, usuarios["b"]) == [(usuarios["tenant_b"], None, "es")]
    assert _tenant_de_usuario(rt, uuid4()) == []


def test_tenant_de_usuario_es_security_definer_con_search_path(rt, usuarios):
    with rt.connect() as c:
        definer, config = c.execute(text(
            "SELECT prosecdef, proconfig FROM pg_proc WHERE oid = 'public.tenant_de_usuario(uuid)'::regprocedure")).one()
        permisos = {rol: c.execute(text("SELECT has_function_privilege(:rol, 'public.tenant_de_usuario(uuid)', 'EXECUTE')"),
                                   {"rol": rol}).scalar() for rol in ("app_rt", "anon", "authenticated")}
    assert definer is True
    assert any(x.startswith("search_path=") for x in config or [])
    assert permisos == {"app_rt": True, "anon": False, "authenticated": False}
