"""Puerta B por la API: POST /intake/frase y GET /intake/estado, contra Postgres con RLS y el proveedor de IA con
transporte falso. IA_API_KEY e IA_MODELO salen del entorno del api; sin ellas (o con un modelo sin tarifa) la API
arranca igual y la ruta responde 503 ia_no_disponible. Nunca hay red ni key real."""
import importlib
import logging
from contextlib import contextmanager
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.anthropic_intake_falso import CLAVE_FALSA, MODELO, SIN_PAIS, VALIDA, respuesta, transporte
from tests.integration.test_auth import _bearer, entorno, usuarios, verificador  # noqa: F401

FRASE = "vendo software contable a ferreterías medianas en Antioquia"
OK = {"IA_API_KEY": CLAVE_FALSA, "IA_MODELO": MODELO}
TARIFA_DEL_MODELO = {"in": Decimal("0.10") / 1_000_000, "out": Decimal("0.50") / 1_000_000}  # config/tarifas.yaml


@contextmanager
def arrancar(entorno, verificador, *respuestas, **env):  # noqa: F811
    """La app tal como arranca el lifespan, con el entorno de IA que se pida y la Messages API falsa."""
    for nombre in ("IA_API_KEY", "IA_MODELO"):
        entorno.delenv(nombre, raising=False)
    for nombre, valor in env.items():
        entorno.setenv(nombre, valor)
    app = importlib.import_module("app.main").app
    with TestClient(app) as c:
        app.state.verificador = verificador
        c.capturados = []
        app.state.transporte_http = transporte(c.capturados, *respuestas)
        yield c


def _filas_de_costos(admin, tenant):
    with admin.connect() as c:
        return c.execute(text("SELECT tipo, unidades, costo_unitario, proveedor, fuente, lead_id, lote_id, gratis "
                              "FROM costos WHERE tenant_id = :t ORDER BY ts, tipo DESC"), {"t": tenant}).all()


def _post(c, quien, frase=FRASE, **extra):
    return c.post("/intake/frase", json={"frase": frase, **extra}, headers=_bearer(quien))


# --- estado ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("env,frase", [
    (OK, True),
    ({}, False),
    ({"IA_API_KEY": CLAVE_FALSA}, False),
    ({"IA_MODELO": MODELO}, False),
    ({"IA_API_KEY": "", "IA_MODELO": MODELO}, False),
    ({"IA_API_KEY": CLAVE_FALSA, "IA_MODELO": "claude-sin-tarifa"}, False),
], ids=["completo", "nada", "sin_modelo", "sin_key", "key_vacia", "modelo_sin_tarifa"])
def test_estado_dice_si_la_puerta_b_esta_disponible(entorno, verificador, usuarios, env, frase):  # noqa: F811
    with arrancar(entorno, verificador, **env) as c:
        r = c.get("/intake/estado", headers=_bearer(usuarios["a"]))

    assert (r.status_code, r.json()) == (200, {"frase": frase, "lookalike": False})


# --- 503: la API arranca igual, la ruta dice que no -----------------------------------------------------------------

@pytest.mark.parametrize("env", [
    {}, {"IA_API_KEY": CLAVE_FALSA}, {"IA_MODELO": MODELO}, {"IA_API_KEY": CLAVE_FALSA, "IA_MODELO": "claude-sin-tarifa"},
], ids=["sin_nada", "sin_modelo", "sin_key", "modelo_sin_tarifa"])
def test_sin_ia_configurada_la_ruta_da_503_y_no_llama_ni_cobra(entorno, verificador, usuarios, admin, env):  # noqa: F811
    with arrancar(entorno, verificador, **env) as c:
        assert c.get("/health").status_code in (200, 503)  # arrancó (503 solo si la base está caída)
        r = _post(c, usuarios["a"])
        pedidos = list(c.capturados)

    assert (r.status_code, r.json()) == (503, {"detail": "ia_no_disponible"})
    assert pedidos == [] and _filas_de_costos(admin, usuarios["tenant_a"]) == []


# --- camino feliz ---------------------------------------------------------------------------------------------------

def test_post_intake_frase_devuelve_sugerencia_con_la_forma_de_vista_previa(entorno, verificador, usuarios):  # noqa: F811
    with arrancar(entorno, verificador, **OK) as c:
        r = _post(c, usuarios["a"])

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["sugerencia"] == {"pais": "CO", "ciiu": "4752", "departamento": "05", "ciudad": None,
                                    "ingresos_min": 500000000, "palabras_clave": ["ferretería"], "exclusiones": []}
    esperado = Decimal(200) * TARIFA_DEL_MODELO["in"] + Decimal(60) * TARIFA_DEL_MODELO["out"]
    assert Decimal(cuerpo["costo_usd"]) == esperado


def test_la_sugerencia_resuelve_codigos_y_descarta_lo_que_no_existe(entorno, verificador, usuarios):  # noqa: F811
    alucinada = {**VALIDA, "ciiu": "9999", "departamento": "Narnia", "ciudad": "Medellín"}
    with arrancar(entorno, verificador, respuesta(alucinada), **OK) as c:
        s = _post(c, usuarios["a"]).json()["sugerencia"]

    # Medellín es única en el país: completa el departamento real; el CIIU fuera de catálogo sale null.
    assert (s["ciiu"], s["departamento"], s["ciudad"]) == (None, "05", "Medellín")


def test_el_costo_queda_en_el_libro_del_tenant_antes_de_responder(entorno, verificador, usuarios, admin):  # noqa: F811
    with arrancar(entorno, verificador, **OK) as c:
        r = _post(c, usuarios["a"])

    filas = _filas_de_costos(admin, usuarios["tenant_a"])
    assert r.status_code == 200
    assert [(f.tipo, f.unidades, f.proveedor, f.fuente, f.lead_id, f.gratis) for f in filas] == [
        ("llm_tokens_in", 200, "anthropic", "intake", None, False), ("llm_tokens_out", 60, "anthropic", "intake", None, False)]
    assert filas[0].lote_id == filas[1].lote_id and filas[0].lote_id is not None
    assert filas[0].costo_unitario == TARIFA_DEL_MODELO["in"]
    assert _filas_de_costos(admin, usuarios["tenant_b"]) == []


def test_el_request_a_anthropic_usa_el_modelo_del_entorno(entorno, verificador, usuarios):  # noqa: F811
    with arrancar(entorno, verificador, **{**OK, "IA_MODELO": "claude-sonnet-5-5"}) as c:
        _post(c, usuarios["a"])
        cuerpo = c.capturados[0]

    assert cuerpo["model"] == "claude-sonnet-5-5" and cuerpo["temperature"] == 0
    assert cuerpo["tool_choice"] == {"type": "tool", "name": "sugerir_icp"}


def test_ninguna_ruta_de_intake_crea_una_fila_en_busquedas(entorno, verificador, usuarios, admin):  # noqa: F811
    with arrancar(entorno, verificador, **OK) as c:
        _post(c, usuarios["a"])
        c.get("/intake/estado", headers=_bearer(usuarios["a"]))

    with admin.connect() as con:
        assert con.execute(text("SELECT count(*) FROM busquedas WHERE tenant_id = :t"),
                           {"t": usuarios["tenant_a"]}).scalar() == 0


# --- entrada --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cuerpo", [
    {"frase": "x" * 501}, {"frase": ""}, {"frase": "   "}, {}, {"frase": 7}, {"frase": FRASE, "tenant_id": "x"},
], ids=["501", "vacia", "espacios", "sin_frase", "no_texto", "campo_extra"])
def test_frase_invalida_da_422_sin_llamar_ni_cobrar(entorno, verificador, usuarios, admin, cuerpo):  # noqa: F811
    with arrancar(entorno, verificador, **OK) as c:
        r = c.post("/intake/frase", json=cuerpo, headers=_bearer(usuarios["a"]))
        pedidos = list(c.capturados)

    assert r.status_code == 422 and "errores" in r.json()
    assert pedidos == [] and _filas_de_costos(admin, usuarios["tenant_a"]) == []


def test_frase_de_500_caracteres_pasa(entorno, verificador, usuarios):  # noqa: F811
    with arrancar(entorno, verificador, **OK) as c:
        assert _post(c, usuarios["a"], frase="x" * 500).status_code == 200


# --- fallas del proveedor -------------------------------------------------------------------------------------------

def test_salida_invalida_dos_veces_da_502_y_cobra_las_dos_llamadas(entorno, verificador, usuarios, admin):  # noqa: F811
    with arrancar(entorno, verificador, respuesta(SIN_PAIS), **OK) as c:
        r = _post(c, usuarios["a"])
        llamadas = len(c.capturados)

    assert (r.status_code, r.json()) == (502, {"detail": "ia_salida_invalida"})
    assert llamadas == 2
    assert len(_filas_de_costos(admin, usuarios["tenant_a"])) == 4


def test_primera_salida_invalida_y_segunda_buena_responde_200(entorno, verificador, usuarios, admin):  # noqa: F811
    with arrancar(entorno, verificador, respuesta(SIN_PAIS), respuesta(VALIDA), **OK) as c:
        r = _post(c, usuarios["a"])

    assert r.status_code == 200 and len(_filas_de_costos(admin, usuarios["tenant_a"])) == 4


def test_timeout_da_502_y_cobra_el_techo(entorno, verificador, usuarios, admin):  # noqa: F811
    with arrancar(entorno, verificador, httpx.ReadTimeout("lento"), **OK) as c:
        r = _post(c, usuarios["a"])

    filas = _filas_de_costos(admin, usuarios["tenant_a"])
    assert (r.status_code, r.json()) == (502, {"detail": "ia_error"})
    assert [f.tipo for f in filas] == ["llm_tokens_in", "llm_tokens_out"] and filas[1].unidades == 512


def test_error_http_del_proveedor_da_502_sin_cobrar_ni_filtrar_la_key(entorno, verificador, usuarios, admin):  # noqa: F811
    with arrancar(entorno, verificador, httpx.Response(401, json={"error": "x"}), **OK) as c:
        r = _post(c, usuarios["a"])

    assert (r.status_code, r.json()) == (502, {"detail": "ia_error"})
    assert CLAVE_FALSA not in r.text and _filas_de_costos(admin, usuarios["tenant_a"]) == []


# --- secretos y datos fuera de los logs -----------------------------------------------------------------------------

SECRETA = {"palabras_clave": ["ZZ-RESPUESTA-456"]}


@pytest.mark.parametrize("respuestas", [(respuesta({**VALIDA, **SECRETA}),), (respuesta({**SIN_PAIS, **SECRETA}),),
                                        (httpx.ReadTimeout("lento"),)], ids=["ok", "salida_invalida", "timeout"])
def test_ni_la_frase_ni_la_key_ni_la_respuesta_salen_en_logs(entorno, verificador, usuarios, caplog, capsys, respuestas):  # noqa: F811
    caplog.set_level(logging.DEBUG)

    with arrancar(entorno, verificador, *respuestas, **OK) as c:
        r = _post(c, usuarios["a"], frase="ferreterías ZZ-FRASE-SECRETA-123")

    salida = capsys.readouterr()
    for secreto in ("ZZ-FRASE-SECRETA-123", "ZZ-RESPUESTA-456", CLAVE_FALSA):
        assert secreto not in caplog.text and secreto not in salida.out and secreto not in salida.err
    # La sugerencia sí devuelve lo que el modelo dijo (es el punto); la frase y la key no vuelven nunca.
    assert "ZZ-FRASE-SECRETA-123" not in r.text and CLAVE_FALSA not in r.text


def test_la_key_no_aparece_en_el_repr_de_los_ajustes(entorno, verificador):  # noqa: F811
    with arrancar(entorno, verificador, **OK) as c:
        assert CLAVE_FALSA not in repr(c.app.state.settings)
