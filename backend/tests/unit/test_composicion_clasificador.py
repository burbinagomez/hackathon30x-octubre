"""Qué clasificador arma `adaptadores_enriquecer`: Jev con TypeSafe, OpenRouter si hay IA, ninguno si no (006, enmienda 2026-10-18)."""
from types import SimpleNamespace

import httpx
from pydantic import SecretStr

from app.composicion import adaptadores_enriquecer, cargar_tarifas
from app.modulos.enriquecimiento.infraestructura.adaptadores.clasificador_openrouter import (
    ClasificadorOpenRouter,
)
from app.modulos.enriquecimiento.infraestructura.adaptadores.jev_clasificador import (
    JevClasificador,
)
from tests.falsos import RegistroCostosFalso

BASE = dict(typesafe_api_key=None, typesafe_url=None, ia_api_key=None, ia_modelo=None, ia_proveedor=None,
            ia_modelo_proveedor=None, datos_gov_co_url=None, datos_gov_co_app_token=None)


def _clasificador(**campos):
    transporte = httpx.MockTransport(lambda r: httpx.Response(500))
    return adaptadores_enriquecer(SimpleNamespace(**{**BASE, **campos}), RegistroCostosFalso(), cargar_tarifas(),
                                  transporte)[2]


TYPESAFE = {"typesafe_api_key": SecretStr("k"), "typesafe_url": "https://jev.invalid"}
IA = {"ia_api_key": SecretStr("k"), "ia_modelo": "claude-haiku-5-5", "ia_proveedor": "openrouter"}


def test_con_typesafe_gana_jev():
    assert isinstance(_clasificador(**TYPESAFE, **IA), JevClasificador)


def test_sin_typesafe_y_con_ia_queda_openrouter():
    assert isinstance(_clasificador(**IA), ClasificadorOpenRouter)


def test_solo_key_de_typesafe_sin_url_y_con_ia_queda_openrouter():
    assert isinstance(_clasificador(typesafe_api_key=SecretStr("k"), **IA), ClasificadorOpenRouter)


def test_sin_nada_no_hay_clasificador():
    assert _clasificador() is None


def test_ia_con_anthropic_no_arma_clasificador():
    assert _clasificador(**{**IA, "ia_proveedor": "anthropic"}) is None
