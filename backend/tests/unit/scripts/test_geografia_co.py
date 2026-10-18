"""scripts/geografia_co.py: arma config/geografia/co.yaml. Sin red: las filas del dataset son sintéticas."""
import importlib.util
import re
from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("geografia_co", BACKEND / "scripts" / "geografia_co.py")
geografia_co = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(geografia_co)

FILAS = [  # forma del dataset DIVIPOLA: cod_dpto, cod_mpio, nom_mpio (en mayúsculas)
    {"cod_dpto": "73", "cod_mpio": "73001", "nom_mpio": "IBAGUÉ"},
    {"cod_dpto": "73", "cod_mpio": "73449", "nom_mpio": "MELGAR"},
    {"cod_dpto": "11", "cod_mpio": "11001", "nom_mpio": "BOGOTÁ, D.C."},
    {"cod_dpto": "05", "cod_mpio": "05045", "nom_mpio": "APARTADÓ"},
    {"cod_dpto": "25", "cod_mpio": "25269", "nom_mpio": "FACATATIVÁ"},
    {"cod_dpto": "27", "cod_mpio": "27001", "nom_mpio": "QUIBDÓ"},
    {"cod_dpto": "76", "cod_mpio": "76001", "nom_mpio": "CALI"},
    {"cod_dpto": "50", "cod_mpio": "50001", "nom_mpio": "VILLAVICENCIO"},
    {"cod_dpto": "05", "cod_mpio": "05250", "nom_mpio": "EL BAGRE"},
    {"cod_dpto": "20", "cod_mpio": "20400", "nom_mpio": "LA JAGUA DE IBIRICO"},
]


def _cargar(texto):
    return yaml.safe_load(texto) or {"pais": None, "divisiones": []}


def test_la_tabla_del_script_tiene_los_33_departamentos_con_codigos_unicos():
    tabla = geografia_co.DEPARTAMENTOS
    assert len(tabla) == 33
    assert len({t[0] for t in tabla}) == 33 and len({t[1] for t in tabla}) == 33
    assert all(re.fullmatch(r"\d{2}", cod) and re.fullmatch(r"CO-[A-Z]{2,3}", iso) and es and en
               for cod, iso, es, en in tabla)
    assert {c: i for c, i, _, _ in tabla}["73"] == "CO-TOL" and {c: i for c, i, _, _ in tabla}["11"] == "CO-DC"


def test_construir_agrupa_los_municipios_por_division_con_codigo_nativo_y_nombre_en_titulo():
    datos = _cargar(geografia_co.construir(FILAS, "2026-10-18", "gdxc-w37w"))

    por_nativo = {d["codigo_nativo"]: d for d in datos["divisiones"]}
    assert len(datos["divisiones"]) == 33 and datos["pais"] == "CO"
    assert por_nativo["73"]["iso_3166_2"] == "CO-TOL"
    assert por_nativo["73"]["municipios"] == [{"codigo_nativo": "73001", "nombre": "Ibagué"},
                                              {"codigo_nativo": "73449", "nombre": "Melgar"}]
    assert por_nativo["11"]["municipios"] == [{"codigo_nativo": "11001", "nombre": "Bogotá, D.C."}]
    assert [m["nombre"] for m in por_nativo["05"]["municipios"]] == ["Apartadó", "El Bagre"]  # por código
    assert [m["nombre"] for m in por_nativo["20"]["municipios"]] == ["La Jagua de Ibirico"]  # "de" en minúscula
    assert por_nativo["91"]["municipios"] == []  # una división sin filas queda sin municipios


def test_construir_rechaza_un_departamento_que_no_esta_en_la_tabla_en_vez_de_inventarlo():
    with pytest.raises(ValueError, match="98"):
        geografia_co.construir([{"cod_dpto": "98", "cod_mpio": "98001", "nom_mpio": "INVENTADO"}], "2026-10-18", "x")


def test_el_encabezado_cita_la_fuente_oficial_el_dataset_y_la_fecha():
    texto = geografia_co.construir(FILAS, "2026-10-18", "gdxc-w37w")
    encabezado = "\n".join(l for l in texto.splitlines() if l.startswith("#"))
    for dato in ("DANE", "DIVIPOLA", "datos.gov.co", "gdxc-w37w", "2026-10-18", "ISO 3166-2"):
        assert dato in encabezado, dato


def test_sin_filas_el_encabezado_dice_que_faltan_los_municipios_y_no_cita_dataset():
    texto = geografia_co.construir([], "2026-10-18", None)
    assert "sin municipios" in "\n".join(l for l in texto.splitlines() if l.startswith("#")).lower()
    assert all(d["municipios"] == [] for d in _cargar(texto)["divisiones"])


def test_el_co_yaml_versionado_sale_de_la_tabla_del_script():
    ruta = BACKEND / "config" / "geografia" / "co.yaml"
    assert ruta.exists()
    datos = _cargar(ruta.read_text())
    assert [(d["codigo_nativo"], d["iso_3166_2"], d["nombre_es"], d["nombre_en"]) for d in datos["divisiones"]] == \
        sorted(geografia_co.DEPARTAMENTOS)
    encabezado = "\n".join(l for l in ruta.read_text().splitlines() if l.startswith("#"))
    assert "DANE" in encabezado and "DIVIPOLA" in encabezado and re.search(r"20\d\d-\d\d-\d\d", encabezado)
