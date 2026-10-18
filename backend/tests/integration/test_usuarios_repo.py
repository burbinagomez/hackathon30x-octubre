"""usuarios: app_rt no la toca; entra solo por tenant_de_usuario (SECURITY DEFINER)."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import db

PRIVILEGIO_INSUFICIENTE = "42501"


@pytest.fixture
def usuarios(admin, tenants):
    """Dos usuarios en A (idioma 'en' y 'es') y uno en B (sin elección), sembrados como postgres. tenants limpia las filas.
    El segundo de A hace que un WHERE por tenant y no por auth_user_id devuelva 2 filas y no 1."""
    ids = {"a": uuid4(), "a2": uuid4(), "b": uuid4(), "tenant_a": tenants["a"], "tenant_b": tenants["b"]}
    with admin.begin() as c:
        c.execute(text("INSERT INTO usuarios (auth_user_id, tenant_id, idioma) VALUES "
                       "(:a, :tenant_a, 'en'), (:a2, :tenant_a, 'es'), (:b, :tenant_b, NULL)"), ids)
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


# Las dos funciones SECURITY DEFINER por las que `app_rt` entra a `usuarios`: sin las dos, el login no
# resuelve el tenant (tenant_de_usuario) o el usuario no puede elegir idioma (fijar_idioma).
FUNCIONES_DE_ACCESO = ["tenant_de_usuario", "fijar_idioma"]


@pytest.mark.parametrize("nombre", FUNCIONES_DE_ACCESO)
def test_funcion_es_security_definer_con_search_path(rt, usuarios, nombre):
    # Se busca por proname y no por `::regprocedure`: si la función no está, el test falla en el assert
    # de la fila faltante y no en un error al resolver el tipo. Una sobrecarga de más también falla acá.
    with rt.connect() as c:
        filas = c.execute(text(
            "SELECT p.oid, p.prosecdef, p.proconfig FROM pg_proc p"
            " JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public' AND p.proname = :nombre"), {"nombre": nombre}).all()
        assert len(filas) == 1, f"public.{nombre} no está (o está sobrecargada)"
        oid, definer, config = filas[0]
        privilegio = text("SELECT has_function_privilege(:rol, CAST(:oid AS oid), 'EXECUTE')")
        permisos = {rol: c.execute(privilegio, {"rol": rol, "oid": oid}).scalar()
                    for rol in ("app_rt", "anon", "authenticated")}
    assert definer is True
    assert any(x.startswith("search_path=") for x in config or [])
    assert permisos == {"app_rt": True, "anon": False, "authenticated": False}


def test_fijar_idioma_no_cruza_tenants(rt, admin, usuarios):
    """Control positivo y después el mismo usuario con el tenant de B.

    El positivo escribe 'en' sobre el usuario de A que estaba en 'es' (un cambio de verdad, no un UPDATE
    sobre el mismo valor), así que la llamada de B pide volver a 'es': sin el `AND tenant_id` se verían las
    dos cosas —la fila de más que devuelve y el idioma cambiado— en vez de una sola.
    """
    with db.unidad_de_trabajo(rt, usuarios["tenant_a"]) as c:
        assert c.execute(text("SELECT fijar_idioma(:uid, 'en')"), {"uid": usuarios["a2"]}).scalar() == 1
    with db.unidad_de_trabajo(rt, usuarios["tenant_b"]) as c:
        assert c.execute(text("SELECT fijar_idioma(:uid, 'es')"), {"uid": usuarios["a2"]}).scalar() == 0
    with admin.connect() as c:
        assert c.execute(text("SELECT idioma FROM usuarios WHERE auth_user_id = :uid"),
                         {"uid": usuarios["a2"]}).scalar() == "en"
