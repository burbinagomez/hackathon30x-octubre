"""Raíz de composición compartida por la CLI y la API: qué fuentes se arman y cómo."""
from pathlib import Path

from app.modulos.descubrimiento.aplicacion.registro import Registro


def registro_api(ruta_yaml: Path, catalogo: dict[str, type]) -> Registro:
    return Registro({}, frozenset())  # esqueleto T032
