from dataclasses import dataclass
from pathlib import Path

import yaml

from app.modulos.descubrimiento.dominio.errores import RegistroInvalido
from app.modulos.descubrimiento.dominio.modelos import MetaFuente


@dataclass(frozen=True)
class Registro:
    fuentes: dict[str, tuple[type, MetaFuente]]  # clave -> (clase, meta)
    sin_implementacion: frozenset[str]  # habilitadas sin clase en el catálogo


# ponytail: una sola sección (fuentes_descubrimiento); se generaliza por sección cuando la 006 cargue otro puerto.
def cargar_registro(ruta_yaml: Path, catalogo: dict[str, type]) -> Registro:
    entradas = (yaml.safe_load(Path(ruta_yaml).read_text()) or {}).get("fuentes_descubrimiento") or {}

    huerfanas = set(catalogo) - set(entradas)
    if huerfanas:
        raise RegistroInvalido(f"claves del catálogo sin entrada en fuentes.yaml: {sorted(huerfanas)}")

    fuentes: dict[str, tuple[type, MetaFuente]] = {}
    sin_implementacion: set[str] = set()
    for clave, e in entradas.items():
        if not e.get("habilitado"):
            continue
        if not e.get("paises") or not e.get("filtros"):
            raise RegistroInvalido(f"{clave}: habilitada sin paises o sin filtros")
        if clave not in catalogo:
            sin_implementacion.add(clave)
            continue
        try:
            meta = MetaFuente(
                clave=clave,
                proveedor=e["proveedor"],
                paises=frozenset(e["paises"]),
                filtros=frozenset(e["filtros"]),
                trae=frozenset(e.get("trae") or ()),
                tipo=e["tipo"],
                licencia=e["licencia"],
                endpoint=e.get("endpoint"),
                tipo_titular_implicito=e.get("tipo_titular_implicito"),
            )
        except KeyError as falta:
            raise RegistroInvalido(f"{clave}: falta {falta}") from None
        fuentes[clave] = (catalogo[clave], meta)
    return Registro(fuentes, frozenset(sin_implementacion))


def cargar_actividades(ruta_yaml: Path) -> dict[str, tuple[str, ...]]:
    """CIIU -> etiquetas OSM, desde config/actividades.yaml."""
    entradas = yaml.safe_load(Path(ruta_yaml).read_text()) or {}
    return {str(ciiu): tuple(e.get("osm") or ()) for ciiu, e in entradas.items()}
