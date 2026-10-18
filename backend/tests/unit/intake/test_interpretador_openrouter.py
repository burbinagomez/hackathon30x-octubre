"""InterpretadorOpenRouter: otro adaptador del mismo puerto GeneradorEstructurado (API compatible con OpenAI de
OpenRouter, tool calling forzado). Transporte falso, sin red. Se conecta por IA_PROVEEDOR=openrouter."""
import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.modulos.intake.dominio.errores import ErrorGeneracion, SalidaIntakeInvalida
from app.modulos.intake.dominio.puertos import GeneradorEstructurado
from app.modulos.intake.infraestructura.llm.interpretador_openrouter import (
    InterpretadorOpenRouter,
)
from tests.falsos import RegistroCostosFalso

TARIFA = {"in_usd_por_M": Decimal("0.10"), "out_usd_por_M": Decimal("0.50")}
CLAVE = "sk-or-falsa"
MODELO = "anthropic/claude-haiku-falso"
FRASE = "vendo software contable a ferreterías medianas en Antioquia"
VALIDA = {"pais": "CO", "ciiu": None, "departamento": "Antioquia", "ciudad": None, "ingresos_min": None,
          "palabras_clave": ["software"], "exclusiones": []}


def _respuesta(argumentos=VALIDA, uso=(120, 40), status=200):
    cuerpo = {"choices": [{"message": {"role": "assistant", "tool_calls": [
        {"type": "function", "function": {"name": "sugerir_icp", "arguments": json.dumps(argumentos)}}]}}]}
    if uso is not None:
        cuerpo["usage"] = {"prompt_tokens": uso[0], "completion_tokens": uso[1]}
    return httpx.Response(status, json=cuerpo)


def _adaptador(costos, *respuestas, capturados=None, cabeceras=None):
    cola = list(respuestas) or [_respuesta()]

    def manejar(request: httpx.Request):
        if capturados is not None:
            capturados.append(json.loads(request.content))
        if cabeceras is not None:
            cabeceras.append(dict(request.headers))
        r = cola.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    http = httpx.Client(base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(manejar))
    return InterpretadorOpenRouter(registro_costos=costos, tarifa=TARIFA, modelo=MODELO, api_key=CLAVE, http_client=http)


def test_cumple_el_puerto_generador_estructurado():
    assert isinstance(_adaptador(RegistroCostosFalso()), GeneradorEstructurado)


def test_devuelve_los_argumentos_de_la_herramienta():
    assert _adaptador(RegistroCostosFalso()).generar(FRASE, uuid4()) == VALIDA


def test_el_request_fuerza_la_herramienta_con_bearer_y_el_modelo_del_proveedor():
    capturados, cabeceras = [], []
    _adaptador(RegistroCostosFalso(), capturados=capturados, cabeceras=cabeceras).generar(FRASE, uuid4())

    cuerpo = capturados[0]
    assert cuerpo["model"] == MODELO and cuerpo["temperature"] == 0
    assert cuerpo["tool_choice"] == {"type": "function", "function": {"name": "sugerir_icp"}}
    assert cuerpo["tools"][0]["function"]["parameters"]["properties"]["pais"]["enum"] == ["CO", "MX", "PE", "BR"]
    assert cuerpo["messages"][0]["role"] == "system" and "frase_a_icp_v1" in cuerpo["messages"][0]["content"]
    assert "<frase>" in cuerpo["messages"][1]["content"]
    assert cabeceras[0]["authorization"] == f"Bearer {CLAVE}"
    assert "x-api-key" not in cabeceras[0]


def test_registra_tokens_con_la_tarifa_y_proveedor_openrouter_antes_de_devolver():
    costos = RegistroCostosFalso()
    lote = uuid4()
    _adaptador(costos).generar(FRASE, lote)

    por_tipo = {o.tipo: o for o in costos.filas}
    assert por_tipo["llm_tokens_in"].unidades == 120 and por_tipo["llm_tokens_out"].unidades == 40
    assert {o.proveedor for o in costos.filas} == {"openrouter"}
    assert {o.fuente for o in costos.filas} == {"intake"} and {o.lote_id for o in costos.filas} == {lote}


def test_sin_usage_legible_cobra_el_techo():
    costos = RegistroCostosFalso()
    _adaptador(costos, _respuesta(uso=None)).generar(FRASE, uuid4())
    salida = next(o for o in costos.filas if o.tipo == "llm_tokens_out")
    assert salida.unidades == 512


def test_http_401_es_error_de_generacion_sin_costo():
    costos = RegistroCostosFalso()
    with pytest.raises(ErrorGeneracion) as e:
        _adaptador(costos, httpx.Response(401, json={"error": {"message": "x"}})).generar(FRASE, uuid4())
    assert e.value.codigo == "http_401" and costos.filas == []


def test_timeout_de_lectura_cobra_el_techo():
    costos = RegistroCostosFalso()
    with pytest.raises(ErrorGeneracion):
        _adaptador(costos, httpx.ReadTimeout("t")).generar(FRASE, uuid4())
    assert len(costos.filas) == 2


def test_argumentos_ilegibles_es_salida_invalida_con_costo_registrado():
    costos = RegistroCostosFalso()
    malo = httpx.Response(200, json={"choices": [{"message": {"tool_calls": [
        {"type": "function", "function": {"name": "sugerir_icp", "arguments": "no es json"}}]}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    with pytest.raises(SalidaIntakeInvalida):
        _adaptador(costos, malo).generar(FRASE, uuid4())
    assert len(costos.filas) == 2
