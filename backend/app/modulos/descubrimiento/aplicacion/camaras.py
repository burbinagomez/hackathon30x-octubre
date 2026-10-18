from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Camara:
    codigo: str
    nombre: str
    municipio_sede: str
    departamentos: frozenset[str]  # códigos DIVIPOLA


def cargar_camaras(ruta: Path) -> dict[str, Camara]:
    entradas = yaml.safe_load(Path(ruta).read_text()) or {}
    return {
        str(codigo): Camara(
            codigo=str(codigo),
            nombre=e["nombre"],
            municipio_sede=e["municipio_sede"],
            departamentos=frozenset(e["departamentos"]),
        )
        for codigo, e in entradas.items()
    }


# ponytail: mapeo a nivel de departamento; sobreincluye (la 04 entra con 25). El dataset no trae municipio.
def camaras_de(camaras: dict[str, Camara], departamento: str) -> set[str]:
    return {c.codigo for c in camaras.values() if departamento in c.departamentos}
