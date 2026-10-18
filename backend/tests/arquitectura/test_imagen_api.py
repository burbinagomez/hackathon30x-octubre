"""La imagen de api lleva todo lo que el lifespan lee de disco: sin config/ no arranca en Railway."""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_la_imagen_copia_config():
    copias = re.findall(r"^COPY\s+(?!--from)(\S+)\s+(\S+)", (BACKEND / "Dockerfile").read_text(), re.M)
    assert ("config/", "./config/") in copias


def test_lo_que_lee_la_api_vive_en_config():
    # main.py y composicion.py leen CONFIG = backend/config; si algo de eso se mueve, este test lo nota.
    for nombre in ("actividades.yaml", "fuentes.yaml", "tarifas.yaml", "camaras_co.yaml", "geografia"):
        assert (BACKEND / "config" / nombre).exists(), nombre
