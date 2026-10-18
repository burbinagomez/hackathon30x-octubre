"""Qué VerificadorTitular arma `adaptadores_enriquecer`: el real si `fuentes.yaml` lo habilita, el stub si no (006, enmienda
2026-10-18). Un flag, nunca un cambio en el dominio ni en el caso de uso."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import yaml

from app.composicion import adaptadores_enriquecer, cargar_tarifas
from app.modulos.enriquecimiento.infraestructura.adaptadores.croma_rues import CromaRues
from app.modulos.enriquecimiento.infraestructura.adaptadores.rues_datos_gov import RuesDatosGov
from tests.falsos import RegistroCostosFalso

# Solo lo que lee la composición; AJUSTES exigiría el entorno completo (DATABASE_URL, etc.).
AJUSTES = SimpleNamespace(typesafe_api_key=None, typesafe_url=None, datos_gov_co_url=None, datos_gov_co_app_token=None)
FUENTES = Path(__file__).resolve().parents[2] / "config" / "fuentes.yaml"


def _yaml(tmp_path, rues: bool, croma: bool):
    config = yaml.safe_load(FUENTES.read_text())
    config["enriquecedores"]["rues_datos_gov_co"]["habilitado"] = rues
    config["enriquecedores"]["croma_rues_co"]["habilitado"] = croma
    ruta = tmp_path / "fuentes.yaml"
    ruta.write_text(yaml.safe_dump(config))
    return ruta


def _verificador(ruta):
    return adaptadores_enriquecer(AJUSTES, RegistroCostosFalso(), cargar_tarifas(),
                                  httpx.MockTransport(lambda r: httpx.Response(200, json=[])), ruta_yaml=ruta)[0]


def test_el_fuentes_yaml_real_habilita_el_verificador_real():
    assert isinstance(_verificador(FUENTES), RuesDatosGov)


def test_desconectado_por_config_queda_el_stub(tmp_path):
    assert isinstance(_verificador(_yaml(tmp_path, rues=False, croma=True)), CromaRues)


def test_el_stub_sigue_diciendo_desconocido(tmp_path):
    v = _verificador(_yaml(tmp_path, rues=False, croma=True)).verificar(uuid4(), "Transportes Andinos", "Bogotá", "CO")

    assert (v.tipo_titular, v.motivo) == ("desconocido", "sin_match")


def test_con_los_dos_habilitados_gana_el_real_y_croma_no_se_consulta(tmp_path):
    assert isinstance(_verificador(_yaml(tmp_path, rues=True, croma=True)), RuesDatosGov)


def test_el_verificador_real_pide_el_timeout_corto_y_un_solo_intento():
    pedidas = []
    transporte = httpx.MockTransport(lambda r: pedidas.append(r) or httpx.Response(503, json={}))
    v = adaptadores_enriquecer(AJUSTES, RegistroCostosFalso(), cargar_tarifas(), transporte, ruta_yaml=FUENTES)[0]

    r = v.verificar(uuid4(), "Transportes Andinos", "Bogotá", "CO")

    assert r.motivo == "fuente_no_disponible" and len(pedidas) == 1  # un lead no retiene al worker con reintentos


def test_sin_ningun_verificador_habilitado_queda_el_stub_cerrado(tmp_path):
    assert isinstance(_verificador(_yaml(tmp_path, rues=False, croma=False)), CromaRues)


def test_el_dataset_declarado_en_el_registro_es_el_que_consulta_el_cliente():
    from app.modulos.descubrimiento.infraestructura.adaptadores.datos_gov_co_rues import URL_DATASET
    from app.modulos.enriquecimiento.infraestructura.adaptadores.rues_datos_gov import DATASET

    declarado = yaml.safe_load(FUENTES.read_text())["enriquecedores"]["rues_datos_gov_co"]["dataset"]

    assert declarado == DATASET and URL_DATASET.endswith(f"/{DATASET}.json")
