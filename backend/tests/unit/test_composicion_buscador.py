"""Qué BuscadorSitioWeb arma `buscador_sitio_web`: el real si `fuentes.yaml` lo habilita, None si no (006, buscador de sitio
web). Un flag, nunca un cambio en el dominio ni en el caso de uso."""
from pathlib import Path

import httpx
import yaml

from app.composicion import buscador_sitio_web, cargar_tarifas
from app.modulos.enriquecimiento.infraestructura.adaptadores.dominio_por_razon_social import DominioPorRazonSocial
from tests.falsos import RegistroCostosFalso

FUENTES = Path(__file__).resolve().parents[2] / "config" / "fuentes.yaml"


def _armar(ruta):
    return buscador_sitio_web(RegistroCostosFalso(), cargar_tarifas(), httpx.MockTransport(lambda r: httpx.Response(404)),
                              resolver=lambda host: [], ruta_yaml=ruta)


def _yaml(tmp_path, habilitado):
    config = yaml.safe_load(FUENTES.read_text())
    config["enriquecedores"]["dominio_por_razon_social"]["habilitado"] = habilitado
    ruta = tmp_path / "fuentes.yaml"
    ruta.write_text(yaml.safe_dump(config))
    return ruta


def test_el_fuentes_yaml_real_lo_habilita():
    assert isinstance(_armar(FUENTES), DominioPorRazonSocial)


def test_desconectado_por_config_no_existe(tmp_path):
    assert _armar(_yaml(tmp_path, False)) is None


def test_sin_la_entrada_en_el_yaml_tampoco_existe(tmp_path):
    config = yaml.safe_load(FUENTES.read_text())
    del config["enriquecedores"]["dominio_por_razon_social"]
    ruta = tmp_path / "fuentes.yaml"
    ruta.write_text(yaml.safe_dump(config))
    assert _armar(ruta) is None
