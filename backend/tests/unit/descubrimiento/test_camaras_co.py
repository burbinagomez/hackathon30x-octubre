from pathlib import Path

from app.modulos.descubrimiento.aplicacion.camaras import camaras_de, cargar_camaras
from app.modulos.enriquecimiento.dominio.normalizar_titular import normalizar_ciudad

CAMARAS_YAML = Path(__file__).resolve().parents[3] / "config" / "camaras_co.yaml"


def test_bogota_y_cundinamarca():
    camaras = cargar_camaras(CAMARAS_YAML)

    assert camaras_de(camaras, "11") == {"04"}
    assert camaras_de(camaras, "25") >= {"04", "14", "47", "58"}


def _geografia_co():
    import yaml

    datos = yaml.safe_load((CAMARAS_YAML.parent / "geografia" / "co.yaml").read_text())
    divisiones = {d["codigo_nativo"] for d in datos["divisiones"]}
    municipios = {normalizar_ciudad(m["nombre"]) for d in datos["divisiones"] for m in d["municipios"]}
    return divisiones, municipios


def test_toda_camara_tiene_municipio_y_departamento_validos_en_la_geografia():
    divisiones, municipios = _geografia_co()
    camaras = cargar_camaras(CAMARAS_YAML)

    assert camaras
    for c in camaras.values():
        assert normalizar_ciudad(c.municipio_sede) in municipios, c.codigo
        assert c.departamentos and c.departamentos <= divisiones, c.codigo


def test_no_hay_codigos_de_camara_repetidos():
    import re

    lineas = CAMARAS_YAML.read_text().splitlines()
    codigos = [m.group(1) for ln in lineas if (m := re.match(r'^"(\d+)":', ln))]

    assert len(codigos) == len(set(codigos))


def test_yaml_real_cubre_las_58_camaras_del_rues():
    # Los 58 códigos de c82u-588k ($group=codigo_camara, consultado 2026-10-18).
    assert set(cargar_camaras(CAMARAS_YAML)) == {f"{i:02d}" for i in range(1, 59)}


def test_casos_puntuales_de_sede_y_departamento():
    c = cargar_camaras(CAMARAS_YAML)
    assert (c["21"].municipio_sede, c["21"].departamentos) == ("Medellín", frozenset({"05"}))
    assert (c["08"].municipio_sede, c["08"].departamentos) == ("Santiago de Cali", frozenset({"76"}))
    assert (c["03"].municipio_sede, c["03"].departamentos) == ("Barranquilla", frozenset({"08"}))
    assert (c["05"].municipio_sede, c["05"].departamentos) == ("Bucaramanga", frozenset({"68"}))


def test_alias_del_nombre_corto_apuntan_a_la_sede():
    from app.modulos.descubrimiento.aplicacion.camaras import alias_de_ciudad

    alias = alias_de_ciudad(cargar_camaras(CAMARAS_YAML), normalizar_ciudad)
    assert alias[normalizar_ciudad("Cali")] == normalizar_ciudad("Santiago de Cali")
    assert alias[normalizar_ciudad("Cúcuta")] == normalizar_ciudad("San José de Cúcuta")
    assert alias[normalizar_ciudad("Cartagena")] == normalizar_ciudad("Cartagena de Indias")
