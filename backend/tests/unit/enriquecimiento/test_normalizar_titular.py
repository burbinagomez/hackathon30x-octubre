"""Normalización de la regla "nombre + ciudad" (enmienda 2026-10-18 de la 006). Es una decisión de cumplimiento: cada
caso fija qué cuenta como el mismo nombre."""
import pytest

from app.modulos.enriquecimiento.dominio.normalizar_titular import normalizar_ciudad, normalizar_nombre


@pytest.mark.parametrize("crudo, esperado", [
    ("Transportes Andinos", "TRANSPORTES ANDINOS"),
    ("  transportes   andinos  ", "TRANSPORTES ANDINOS"),
    ("Logística Ñandú", "LOGISTICA NANDU"),          # tildes y eñe
    ("Carga & Cía. del Sur", "CARGA CIA DEL SUR"),   # puntuación separa palabras
    ("Los Andes-Express", "LOS ANDES EXPRESS"),
])
def test_mayusculas_sin_tildes_sin_puntuacion_espacios_colapsados(crudo, esperado):
    assert normalizar_nombre(crudo) == esperado


@pytest.mark.parametrize("crudo", [
    "Transportes Andinos S.A.S.", "TRANSPORTES ANDINOS SAS", "Transportes Andinos Ltda.", "Transportes Andinos S.A.",
    "Transportes Andinos E.U.", "Transportes Andinos S.A.S. LTDA",
])
def test_los_sufijos_societarios_al_final_se_ignoran(crudo):
    assert normalizar_nombre(crudo) == "TRANSPORTES ANDINOS"


def test_un_sufijo_en_medio_del_nombre_no_se_toca():
    assert normalizar_nombre("SA Andinos Express") == "SA ANDINOS EXPRESS"


def test_un_nombre_que_solo_es_sufijo_queda_vacio():
    assert normalizar_nombre("S.A.S.") == ""
    assert normalizar_nombre("   ") == ""


def test_la_ciudad_se_normaliza_igual_y_no_pierde_su_ultima_palabra():
    assert normalizar_ciudad(" Bogotá ") == "BOGOTA"
    assert normalizar_ciudad("Medellín") == "MEDELLIN"
    assert normalizar_ciudad("Santa Marta") == "SANTA MARTA"


@pytest.mark.parametrize("crudo", ["Bogotá D.C.", "BOGOTA DC", "Bogotá, D. C."])
def test_bogota_dc_es_bogota(crudo):
    assert normalizar_ciudad(crudo) == "BOGOTA"


def test_la_ciudad_no_ignora_sufijos_societarios():
    assert normalizar_ciudad("Sa") == "SA"
