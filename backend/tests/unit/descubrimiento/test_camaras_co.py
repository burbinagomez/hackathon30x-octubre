from pathlib import Path

from app.modulos.descubrimiento.aplicacion.camaras import camaras_de, cargar_camaras

CAMARAS_YAML = Path(__file__).resolve().parents[3] / "config" / "camaras_co.yaml"


def test_bogota_y_cundinamarca():
    camaras = cargar_camaras(CAMARAS_YAML)

    assert camaras_de(camaras, "11") == {"04"}
    assert camaras_de(camaras, "25") >= {"04", "14", "47", "58"}
