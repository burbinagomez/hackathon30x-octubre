"""Croma (de pago) entra a la API solo mientras el tope de gasto esté aplicado. Guardas de composición:
si alguien quita el tope de EjecutarBorrador o los límites del YAML, esto se pone rojo."""
import inspect
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import yaml
from pydantic import SecretStr

from app.composicion import cargar_tarifas, fabrica_de_fuentes, registro_api
from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBorrador
from app.modulos.descubrimiento.aplicacion.registro import cargar_actividades
from app.modulos.descubrimiento.dominio.errores import LimiteFuenteAgotado, TopeExcedido
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo
from tests.falsos import RegistroCostosFalso, RepositorioLeadsFalso

BACKEND = Path(__file__).resolve().parents[3]
FUENTES_YAML = BACKEND / "config" / "fuentes.yaml"
ICP = CriteriosICP("CO", {"ciiu": "4711", "departamento": "11"})


def _fabrica(costos, pedidas):
    registro = registro_api(FUENTES_YAML, catalogo)
    ajustes = SimpleNamespace(datos_gov_co_url=None, datos_gov_co_app_token=None, overpass_url=None,
                              croma_base_url=None, repo_url="https://x.test")
    limites = (yaml.safe_load(FUENTES_YAML.read_text()) or {}).get("limites") or {}  # lo que carga app.main
    return fabrica_de_fuentes(
        registro, ajustes=lambda: ajustes, costos=costos, tarifas=cargar_tarifas(), limites=limites,
        api_key=SecretStr("clave-de-prueba"),
        transporte=lambda: httpx.MockTransport(lambda r: pedidas.append(r) or httpx.Response(200, json={})))


def test_el_registro_de_la_api_arma_croma_osm_y_datos_gov():
    registro = registro_api(FUENTES_YAML, catalogo)

    assert {"croma_supersociedades_co", "osm_overpass", "datos_gov_co_rues"} <= set(registro.fuentes)


def test_croma_sin_clase_en_el_catalogo_queda_sin_implementacion_y_no_rompe():
    sin_croma = {c: k for c, k in catalogo.items() if not c.startswith("croma_")}  # lo que hace app.main sin CROMA_API_KEY

    registro = registro_api(FUENTES_YAML, sin_croma)

    assert "croma_supersociedades_co" not in registro.fuentes
    assert "croma_supersociedades_co" in registro.sin_implementacion


def test_con_croma_en_la_api_el_tope_corta_antes_de_cualquier_request():
    pedidas, costos, repo = [], RegistroCostosFalso(), RepositorioLeadsFalso()
    caso = EjecutarBorrador(repo, _fabrica(costos, pedidas),
                            cargar_actividades(BACKEND / "config" / "actividades.yaml"), costos)
    borrador = repo.crear_borrador(ICP, "email", Decimal("0.0001"), None)  # menos que el peor caso de cualquiera

    with pytest.raises(TopeExcedido):
        caso.ejecutar(borrador)

    assert pedidas == [] and costos.filas == [] and repo.busquedas[borrador] == "borrador"


def test_ejecutar_borrador_no_se_puede_armar_sin_el_libro_de_costos():
    assert inspect.signature(EjecutarBorrador.__init__).parameters["costos"].default is inspect.Parameter.empty


def test_los_limites_de_croma_salen_de_fuentes_yaml_via_composicion():
    limites = yaml.safe_load(FUENTES_YAML.read_text())["limites"]
    assert (limites["croma_requests_por_24h"], limites["croma_creditos_gratis_mes"]) == (100, 1500)
    pedidas = []

    por_requests = _fabrica(RegistroCostosFalso(requests_24h=100), pedidas)(uuid4())["croma_supersociedades_co"]
    with pytest.raises(LimiteFuenteAgotado):
        por_requests.buscar(CriteriosICP("CO", {"ciiu": "4711"}), 1)
    por_creditos = _fabrica(RegistroCostosFalso(creditos_mes=Decimal(1500)), pedidas)(uuid4())["croma_supersociedades_co"]
    with pytest.raises(LimiteFuenteAgotado):
        por_creditos.buscar(CriteriosICP("CO", {"ciiu": "4711"}), 1)

    assert pedidas == []
