"""Contrato del puerto VerificadorTitular, parametrizado sobre el registro (`enriquecedores` con `puerto: VerificadorTitular`
en fuentes.yaml). Cada adaptador, el stub que falla cerrado y el real de nombre + ciudad, pasa los mismos tests con la
fuente falsa. Un verificador nuevo en el registro sin entrada acá hace fallar el primer test."""
import importlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import yaml

from app.composicion import adaptadores_enriquecer, cargar_tarifas
from app.modulos.enriquecimiento.dominio.puertos import VerificacionTitular
from tests.falsos import RegistroCostosFalso

FUENTES_YAML = Path(__file__).resolve().parents[2] / "config" / "fuentes.yaml"
AJUSTES = SimpleNamespace(typesafe_api_key=None, typesafe_url=None, datos_gov_co_url=None, datos_gov_co_app_token=None)
NOMBRE_SECRETO = "Zxqvk Ficticia Andina"
FILA = {"nit": "900111222", "digito_verificacion": "1", "razon_social": "ZXQVK FICTICIA ANDINA SAS",
        "cod_ciiu_act_econ_pri": "4923", "codigo_camara": "04", "estado_matricula": "ACTIVA",
        "organizacion_juridica": "SOCIEDADES POR ACCIONES SIMPLIFICADAS SAS", "fecha_renovacion": "20260410"}


def _registrados() -> dict[str, dict]:
    enriquecedores = yaml.safe_load(FUENTES_YAML.read_text())["enriquecedores"]
    return {k: e for k, e in enriquecedores.items() if e.get("puerto") == "VerificadorTitular"}


# Fuentes falsas con las que se prueba cada adaptador: lo que el proveedor puede hacer (datos, nada, caerse, colgarse).
def _fuente(modo):
    def responder(request):
        if modo == "timeout":
            raise httpx.ReadTimeout("lento", request=request)
        return {"match": httpx.Response(200, json=[FILA]), "vacia": httpx.Response(200, json=[]),
                "caida": httpx.Response(503, json={}), "basura": httpx.Response(200, json=["no", "es", "un", "dict"])}[modo]
    return responder


def _armar(clave, tmp_path, modo):
    config = yaml.safe_load(FUENTES_YAML.read_text())
    for k in _registrados():
        config["enriquecedores"][k]["habilitado"] = k == clave
    ruta = tmp_path / "fuentes.yaml"
    ruta.write_text(yaml.safe_dump(config))
    pedidas, costos = [], RegistroCostosFalso()
    transporte = httpx.MockTransport(lambda r: pedidas.append(r) or _fuente(modo)(r))
    return adaptadores_enriquecer(AJUSTES, costos, cargar_tarifas(), transporte, ruta_yaml=ruta)[0], pedidas, costos


CLAVES = ["croma_rues_co", "rues_datos_gov_co"]
MODOS = ["match", "vacia", "caida", "timeout", "basura"]


def test_el_registro_y_la_suite_cubren_los_mismos_verificadores():
    assert set(_registrados()) == set(CLAVES)  # un verificador nuevo obliga a sumarlo acá


@pytest.mark.parametrize("clave", CLAVES)
def test_el_adaptador_armado_es_el_declarado_en_el_registro(clave, tmp_path):
    verificador, _, _ = _armar(clave, tmp_path, "match")
    ruta = _registrados()[clave]["adaptador"]
    modulo, _, clase = ruta.rpartition(".")

    assert type(verificador) is getattr(importlib.import_module(modulo), clase)


@pytest.mark.parametrize("modo", MODOS)
@pytest.mark.parametrize("clave", CLAVES)
def test_siempre_devuelve_una_verificacion_y_nunca_lanza(clave, modo, tmp_path):
    verificador, _, _ = _armar(clave, tmp_path, modo)

    r = verificador.verificar(uuid4(), NOMBRE_SECRETO, "Bogotá")

    assert isinstance(r, VerificacionTitular)
    assert r.tipo_titular in {"juridica", "desconocido"}


@pytest.mark.parametrize("modo", ["vacia", "caida", "timeout", "basura"])
@pytest.mark.parametrize("clave", CLAVES)
def test_sin_evidencia_de_la_fuente_falla_cerrado(clave, modo, tmp_path):
    verificador, _, _ = _armar(clave, tmp_path, modo)

    assert verificador.verificar(uuid4(), NOMBRE_SECRETO, "Bogotá").tipo_titular == "desconocido"


@pytest.mark.parametrize("ciudad", [None, ""])
@pytest.mark.parametrize("clave", CLAVES)
def test_sin_ciudad_nunca_es_juridica(clave, ciudad, tmp_path):
    verificador, _, _ = _armar(clave, tmp_path, "match")

    assert verificador.verificar(uuid4(), NOMBRE_SECRETO, ciudad).tipo_titular == "desconocido"


@pytest.mark.parametrize("modo", MODOS)
@pytest.mark.parametrize("clave", CLAVES)
def test_juridica_solo_con_match_unico_y_con_constancia_coherente(clave, modo, tmp_path):
    verificador, _, _ = _armar(clave, tmp_path, modo)

    r = verificador.verificar(uuid4(), NOMBRE_SECRETO, "Bogotá")

    if r.tipo_titular == "juridica":
        assert r.motivo == "match_unico" and r.constancia is not None and r.constancia.nit
    else:
        assert r.motivo != "match_unico"
    if r.constancia is not None:
        assert r.constancia.motivo == r.motivo


@pytest.mark.parametrize("modo", ["vacia", "caida", "timeout", "basura"])
@pytest.mark.parametrize("clave", CLAVES)
def test_lo_que_no_es_match_no_repite_el_nombre_del_lead(clave, modo, tmp_path):
    verificador, _, _ = _armar(clave, tmp_path, modo)

    assert "zxqvk" not in repr(verificador.verificar(uuid4(), NOMBRE_SECRETO, "Bogotá")).lower()


@pytest.mark.parametrize("modo", MODOS)
@pytest.mark.parametrize("clave", CLAVES)
def test_cada_request_deja_su_fila_de_costos_con_el_lead_antes_de_devolver(clave, modo, tmp_path):
    verificador, pedidas, costos = _armar(clave, tmp_path, modo)
    lead = uuid4()

    verificador.verificar(lead, NOMBRE_SECRETO, "Bogotá")

    assert len(costos.filas) >= len(pedidas)
    assert {f.lead_id for f in costos.filas} <= {lead}
