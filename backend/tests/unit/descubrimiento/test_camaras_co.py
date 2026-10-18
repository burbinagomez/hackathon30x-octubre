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
