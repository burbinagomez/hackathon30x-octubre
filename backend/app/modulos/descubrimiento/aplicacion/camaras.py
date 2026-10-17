from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Camara:
    codigo: str
    nombre: str
    municipio_sede: str
    departamentos: frozenset[str]  # códigos DIVIPOLA


def cargar_camaras(ruta: Path) -> dict[str, Camara]:
    return {}


def camaras_de(camaras: dict[str, Camara], departamento: str) -> set[str]:
    return set()
