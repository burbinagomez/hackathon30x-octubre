"""Contrato del puerto FuenteDescubrimiento, parametrizado sobre el catálogo (T016, parte del tope).

Por ahora solo `costo_maximo_llamada`: el tope de gasto lo usa para decidir antes de cada llamada, y un adaptador que
dejara el default 0 entraría al tope como gratis. El resto de la suite de contrato (contar, normalización, costo
antes de devolver) llega con T016 completa."""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.composicion import armador_de_fuente, cargar_tarifas
from app.modulos.descubrimiento.aplicacion.registro import cargar_registro
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo
from tests.falsos import RegistroCostosFalso

BACKEND = Path(__file__).resolve().parents[2]
FUENTES_YAML = BACKEND / "config" / "fuentes.yaml"

assert catalogo, "catálogo vacío: la suite no correría nada"

# Fórmulas del plan (spec 005, "Tope de gasto"), con las tarifas de config/tarifas.yaml:
#   croma: 1 crédito x 0.00099 (los intentos fallidos registran 0)
#   osm: 2 intentos x 30 s x 0.0000070
#   datos_gov_co_rues: 2 requests x 2 intentos x 30 s x 0.0000070 (spec 011)
ESPERADO = {
    "croma_supersociedades_co": Decimal("0.00099"),
    "osm_overpass": Decimal("0.00042"),
    "datos_gov_co_rues": Decimal("0.00084"),
}


def _armar(clave):
    registro = cargar_registro(FUENTES_YAML, catalogo)
    clase, meta = registro.fuentes[clave]
    ajustes = SimpleNamespace(datos_gov_co_url=None, datos_gov_co_app_token=None, overpass_url=None, croma_base_url=None, repo_url="https://x.test")
    armar = armador_de_fuente(
        clase, meta, ajustes=lambda: ajustes, costos=RegistroCostosFalso(), tarifas=cargar_tarifas(),
        limites={"croma_requests_por_24h": 100, "croma_creditos_gratis_mes": 1500}, api_key=SecretStr("clave-de-prueba"),
        transporte=lambda: httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    return armar(uuid4())


def test_el_catalogo_y_la_tabla_de_esperados_cubren_las_mismas_fuentes():
    assert set(ESPERADO) == set(catalogo)  # un adaptador nuevo obliga a declarar su costo máximo acá


@pytest.mark.parametrize("clave", sorted(catalogo))
def test_costo_maximo_llamada_positivo(clave):
    meta = _armar(clave).meta

    assert type(meta.costo_maximo_llamada) is Decimal
    assert meta.costo_maximo_llamada > 0  # el default 0 dejaría entrar al tope a un adaptador sin declarar


@pytest.mark.parametrize("clave", sorted(catalogo))
def test_costo_maximo_llamada_vale_lo_de_la_formula(clave):
    assert _armar(clave).meta.costo_maximo_llamada == ESPERADO[clave]
