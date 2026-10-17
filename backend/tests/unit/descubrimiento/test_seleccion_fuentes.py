from pathlib import Path

from app.modulos.descubrimiento.aplicacion.registro import cargar_actividades

ACTIVIDADES_YAML = Path(__file__).resolve().parents[3] / "config" / "actividades.yaml"


def test_actividades_yaml_real_carga_y_mapea_4711():
    actividades = cargar_actividades(ACTIVIDADES_YAML)

    assert set(actividades.get("4711", ())) == {"shop=supermarket", "shop=convenience"}
