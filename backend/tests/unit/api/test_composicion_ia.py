"""Puerta B: el proveedor de IA se elige por config (IA_PROVEEDOR). Mismo puerto, otro adaptador; el dominio no cambia."""
from decimal import Decimal
from types import SimpleNamespace

import httpx
from pydantic import SecretStr

from app.composicion import generador_de_frase, ia_configurada
from app.modulos.intake.infraestructura.llm.interpretador_claude import (
    InterpretadorClaude,
)
from app.modulos.intake.infraestructura.llm.interpretador_openrouter import (
    InterpretadorOpenRouter,
)
from tests.falsos import RegistroCostosFalso

TARIFAS = {"claude-haiku-5-5": {"in_usd_por_M": Decimal("0.10"), "out_usd_por_M": Decimal("0.50")}}
TRANSPORTE = httpx.MockTransport(lambda r: httpx.Response(500))


def _ajustes(**cambios):
    base = {"ia_api_key": SecretStr("k"), "ia_modelo": "claude-haiku-5-5", "ia_proveedor": None, "ia_modelo_proveedor": None}
    return SimpleNamespace(**{**base, **cambios})


def test_sin_proveedor_es_anthropic():
    g = generador_de_frase(_ajustes(), TARIFAS, RegistroCostosFalso(), TRANSPORTE)
    assert isinstance(g, InterpretadorClaude)


def test_openrouter_usa_su_adaptador_su_url_y_el_modelo_del_proveedor():
    g = generador_de_frase(_ajustes(ia_proveedor="openrouter", ia_modelo_proveedor="anthropic/claude-x"),
                           TARIFAS, RegistroCostosFalso(), TRANSPORTE)
    assert isinstance(g, InterpretadorOpenRouter)
    assert str(g._http.base_url).rstrip("/") == "https://openrouter.ai/api/v1"
    assert g._modelo == "anthropic/claude-x"


def test_openrouter_sin_modelo_del_proveedor_usa_ia_modelo():
    g = generador_de_frase(_ajustes(ia_proveedor="openrouter"), TARIFAS, RegistroCostosFalso(), TRANSPORTE)
    assert g._modelo == "claude-haiku-5-5"


def test_proveedor_desconocido_apaga_la_puerta():
    assert not ia_configurada(_ajustes(ia_proveedor="otro"), TARIFAS)
    assert generador_de_frase(_ajustes(ia_proveedor="otro"), TARIFAS, RegistroCostosFalso(), TRANSPORTE) is None


def test_la_tarifa_se_busca_por_ia_modelo_no_por_el_nombre_del_proveedor():
    assert ia_configurada(_ajustes(ia_proveedor="openrouter", ia_modelo_proveedor="anthropic/nombre-raro"), TARIFAS)
