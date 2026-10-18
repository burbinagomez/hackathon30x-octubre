"""Auth por la API (T029, security). Sin red: el JWKS es un par EC P-256 local inyectado en `app.state.verificador`."""
import importlib
import logging
import re
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.api import RUTAS_PUBLICAS
from app.api.sesion import tenant_actual
from app.config import SettingsApi
from app.modulos.acceso.infraestructura.verificador_jwks import VerificadorJwks
from tests.integration.conftest import _url
from tests.unit.acceso.test_verificar_token import (
    CASOS_INVALIDOS, ISSUER, PUBLICA, JwksCaido, JwksLocal, _claims, _emitir,
)

JWKS_URL = "https://proyecto.example/auth/v1/.well-known/jwks.json"
ORIGEN = "https://web.example"


def _app():
    # test_cors recarga app.main: el `app` del import de arriba puede ser uno viejo.
    return importlib.import_module("app.main").app


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _url("TEST_DATABASE_URL"))
    monkeypatch.setenv("AUTH_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("AUTH_ISSUER", ISSUER)
    monkeypatch.setenv("CORS_ORIGINS", ORIGEN)
    return monkeypatch


@pytest.fixture
def verificador():
    return VerificadorJwks(JwksLocal(PUBLICA), issuer=ISSUER)


@pytest.fixture
def cliente(entorno, verificador):
    app = _app()
    with TestClient(app) as c:
        app.state.verificador = verificador  # en producción lo arma el lifespan con el PyJWKClient real
        yield c


@pytest.fixture
def usuarios(admin, tenants):
    """a y a2 en el tenant A (idioma 'en' y 'es'), b en el B (sin elección). `tenants` limpia las filas."""
    ids = {"a": uuid4(), "a2": uuid4(), "b": uuid4(), "tenant_a": tenants["a"], "tenant_b": tenants["b"]}
    with admin.begin() as c:
        c.execute(text("INSERT INTO usuarios (auth_user_id, tenant_id, idioma) VALUES "
                       "(:a, :tenant_a, 'en'), (:a2, :tenant_a, 'es'), (:b, :tenant_b, NULL)"), ids)
        # idioma_tenant distinto en B: si la consulta mira el tenant equivocado, el 'es' de A delata el cruce.
        c.execute(text("UPDATE tenants SET idioma = 'en' WHERE id = :tenant_b"), ids)
    return ids


def _bearer(sub, **claims):
    return {"Authorization": f"Bearer {_emitir(_claims(sub=str(sub), **claims))}"}


def _sonda(verificador, engine):
    """Una app mínima con la misma dependencia: `/usuarios/me` no expone el tenant y acá hay que verlo."""
    app = FastAPI()
    app.state.verificador = verificador
    app.state.engine = engine

    @app.get("/sonda")
    def sonda(tenant_id=Depends(tenant_actual)):
        return {"tenant_id": str(tenant_id)}

    return TestClient(app)


def test_el_lifespan_arma_el_verificador_real_con_la_url_y_el_timeout(entorno):
    app = _app()
    with TestClient(app):  # antes de que ningún test inyecte un falso
        v = getattr(app.state, "verificador", None)
        assert isinstance(v, VerificadorJwks)
        cliente = getattr(v, "_cliente", None)
        assert isinstance(cliente, jwt.PyJWKClient)
        assert cliente.uri == JWKS_URL
        assert cliente.timeout == 5
        assert v._issuer == ISSUER


# --- el tenant sale de `usuarios`, nunca del token ---------------------------------------------------------------

def test_token_valido_resuelve_el_tenant_desde_usuarios(rt, verificador, usuarios):
    cliente = _sonda(verificador, rt)
    ajeno = {"tenant_id": str(usuarios["tenant_b"]), "user_metadata": {"tenant_id": str(usuarios["tenant_b"])},
             "app_metadata": {"tenant_id": str(usuarios["tenant_b"])}}

    como_a = cliente.get("/sonda", headers=_bearer(usuarios["a"], **ajeno))
    como_b = cliente.get("/sonda", headers=_bearer(usuarios["b"]))

    assert (como_a.status_code, como_a.json()) == (200, {"tenant_id": str(usuarios["tenant_a"])})
    assert (como_b.status_code, como_b.json()) == (200, {"tenant_id": str(usuarios["tenant_b"])})


def test_token_valido_sin_fila_en_usuarios_da_403(cliente, admin, usuarios):
    sin_fila = cliente.get("/usuarios/me", headers=_bearer(uuid4()))
    assert (sin_fila.status_code, sin_fila.json()) == (403, {"detail": "sin_acceso"})

    headers = _bearer(usuarios["a"])  # el mismo token
    assert cliente.get("/usuarios/me", headers=headers).status_code == 200
    with admin.begin() as c:
        c.execute(text("DELETE FROM usuarios WHERE auth_user_id = :a"), usuarios)
    revocado = cliente.get("/usuarios/me", headers=headers)
    assert (revocado.status_code, revocado.json()) == (403, {"detail": "sin_acceso"})


# --- sin token / token inválido / JWKS caído ---------------------------------------------------------------------

def _rutas():
    # FastAPI 0.143 anida los routers en `_IncludedRouter`: `app.routes` ya no los lista planos. El esquema OpenAPI
    # trae método + ruta completa de todas las rutas de la API (ninguna lleva include_in_schema=False).
    return [(m.upper(), ruta) for ruta, ops in _app().openapi()["paths"].items() if ruta not in RUTAS_PUBLICAS for m in ops]


@pytest.mark.parametrize("metodo,ruta", _rutas(), ids=lambda v: v)
def test_sin_token_da_401(cliente, metodo, ruta):
    url = re.sub(r"\{[^}]+\}", str(uuid4()), ruta)
    r = cliente.request(metodo, url)
    assert (r.status_code, r.json()) == (401, {"detail": "no_autenticado"})


def test_todas_las_rutas_de_los_routers_estan_en_el_esquema():
    # `_rutas()` sale de OpenAPI: una ruta con include_in_schema=False escaparía de test_sin_token_da_401.
    incluidos = [r for r in _app().routes if type(r).__name__ == "_IncludedRouter"]
    assert incluidos
    ocultas = [r.path for i in incluidos for r in i.original_router.routes
               if isinstance(r, APIRoute) and not r.include_in_schema]
    assert ocultas == []


def test_hay_rutas_que_probar():
    assert ("GET", "/usuarios/me") in _rutas()


def test_rutas_publicas_son_exactamente_estas():
    # Literal a propósito: sumar una ruta pública exige tocar este test (y que alguien lo revise).
    assert RUTAS_PUBLICAS == {"/health", "/baja/{token}"}
    assert RUTAS_PUBLICAS <= set(_app().openapi()["paths"])


@pytest.mark.parametrize("caso", sorted(CASOS_INVALIDOS))
def test_token_invalido_da_401(cliente, caso):
    r = cliente.get("/usuarios/me", headers={"Authorization": f"Bearer {CASOS_INVALIDOS[caso]()}"})
    assert (r.status_code, r.json()) == (401, {"detail": "no_autenticado"})


@pytest.mark.parametrize("header", ["Basic abc", "Bearer", "Bearer ", "abc"])
def test_authorization_que_no_es_bearer_da_401(cliente, header):
    r = cliente.get("/usuarios/me", headers={"Authorization": header})
    assert (r.status_code, r.json()) == (401, {"detail": "no_autenticado"})


@pytest.mark.parametrize("formato", ["Basic {t}", "{t}", "Bearer  {t}", "bearer {t}"])
def test_authorization_con_token_valido_pero_mal_formado_da_401(cliente, usuarios, formato):
    # Con un token VÁLIDO: si el parseo del header fuera laxo, estos pasarían. Solo `Bearer <token>` vale.
    token = _emitir(_claims(sub=str(usuarios["a"])))
    r = cliente.get("/usuarios/me", headers={"Authorization": formato.format(t=token)})
    assert (r.status_code, r.json()) == (401, {"detail": "no_autenticado"})


def test_token_valido_por_query_string_sin_header_da_401(cliente, usuarios):
    token = _emitir(_claims(sub=str(usuarios["a"])))
    r = cliente.get("/usuarios/me", params={"access_token": token})
    assert (r.status_code, r.json()) == (401, {"detail": "no_autenticado"})


def test_jwks_inaccesible_da_503(cliente):
    _app().state.verificador = VerificadorJwks(JwksCaido(), issuer=ISSUER)
    token = _emitir(_claims())

    r = cliente.get("/usuarios/me", headers={"Authorization": f"Bearer {token}"})

    assert (r.status_code, r.json()) == (503, {"detail": "auth_no_disponible"})
    assert "sin red" not in r.text and token not in r.text  # ningún detalle de la excepción en el body


@pytest.mark.parametrize("faltante", ["AUTH_JWKS_URL", "AUTH_ISSUER"])
def test_app_no_arranca_sin_auth_jwks_url_ni_issuer(entorno, faltante):
    entorno.delenv(faltante)
    with pytest.raises(ValidationError):
        SettingsApi(_env_file=None)
    entorno.setenv(faltante, "")  # vacío tampoco vale
    with pytest.raises(ValidationError):
        SettingsApi(_env_file=None)


# --- superficie: docs, CORS, logs --------------------------------------------------------------------------------

@pytest.mark.parametrize("ruta", ["/docs", "/redoc", "/openapi.json"])
def test_docs_desactivadas(cliente, ruta):
    assert cliente.get(ruta).status_code == 404


@pytest.fixture
def app_con_docs(monkeypatch):
    def _armar(valor):
        if valor is None:
            monkeypatch.delenv("DOCS_HABILITADAS", raising=False)
        else:
            monkeypatch.setenv("DOCS_HABILITADAS", valor)
        return importlib.reload(importlib.import_module("app.main")).app
    yield _armar
    monkeypatch.delenv("DOCS_HABILITADAS", raising=False)
    importlib.reload(importlib.import_module("app.main"))


@pytest.mark.parametrize("ruta", ["/docs", "/openapi.json"])
def test_docs_se_activan_solo_con_docs_habilitadas_true(app_con_docs, ruta):
    # Interruptor de Railway: por defecto apagadas; "true" exacto las prende. Sin lifespan: no toca la base.
    assert TestClient(app_con_docs("true")).get(ruta).status_code == 200
    for apagado in (None, "", "false", "1", "TRUE "):
        assert TestClient(app_con_docs(apagado)).get(ruta).status_code == 404, apagado


@pytest.fixture
def app_con_origen(entorno):
    yield importlib.reload(importlib.import_module("app.main")).app
    entorno.undo()
    importlib.reload(importlib.import_module("app.main"))


def _preflight(app, origen):
    return TestClient(app).options("/usuarios/me", headers={
        "Origin": origen, "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization"})


def test_cors_solo_permite_web_origin(app_con_origen):
    propio = _preflight(app_con_origen, ORIGEN)
    ajeno = _preflight(app_con_origen, "https://malo.example")

    # El front manda Authorization cross-origin: sin esto el preflight del navegador falla. (PATCH: Pulido.)
    assert propio.status_code == 200
    assert propio.headers.get("access-control-allow-origin") == ORIGEN
    assert "authorization" in propio.headers.get("access-control-allow-headers", "").lower()
    assert "GET" in propio.headers.get("access-control-allow-methods", "")
    assert "access-control-allow-origin" not in ajeno.headers
    # Bearer en header, no cookies: con credenciales el navegador mandaría cookies a un origen que no controlamos.
    assert "access-control-allow-credentials" not in propio.headers


def test_token_no_aparece_en_logs(cliente, usuarios, caplog):
    caplog.set_level(logging.DEBUG)
    bueno = _emitir(_claims(sub=str(usuarios["a"])))
    malo = CASOS_INVALIDOS["otra_clave"]()

    cliente.get("/usuarios/me", headers={"Authorization": f"Bearer {bueno}"})
    cliente.get("/usuarios/me", headers={"Authorization": f"Bearer {malo}"})
    _app().state.verificador = VerificadorJwks(JwksCaido(), issuer=ISSUER)
    cliente.get("/usuarios/me", headers={"Authorization": f"Bearer {bueno}"})

    assert bueno not in caplog.text and malo not in caplog.text


# --- GET /usuarios/me --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("quien,esperado,del_tenant", [("a", "en", "es"), ("a2", "es", "es"), ("b", None, "en")])
def test_usuarios_me_devuelve_idioma(cliente, usuarios, quien, esperado, del_tenant):
    r = cliente.get("/usuarios/me", headers=_bearer(usuarios[quien]))

    # `null` es "no eligió": el front cae al idioma del tenant. Nunca se rellena con el del tenant.
    assert (r.status_code, r.json()) == (200, {"idioma_usuario": esperado, "idioma_tenant": del_tenant})
