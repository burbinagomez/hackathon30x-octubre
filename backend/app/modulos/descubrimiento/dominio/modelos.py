from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, NamedTuple


class Actividad(NamedTuple):  # NamedTuple: se compara con ("4711", "CIIU")
    codigo: str
    sistema: str  # "CIIU" | "SCIAN" | "CNAE"


TipoTitular = Literal["juridica", "natural", "desconocido"]


@dataclass(frozen=True)
class CriteriosICP:
    pais: str  # ISO 3166-1 alfa-2, mayúsculas
    filtros: Mapping[str, str | tuple[str, ...]]  # vocabulario de fuentes.yaml; tupla = varios valores


@dataclass(frozen=True)
class EmpresaCruda:
    pais: str
    nombre: str
    fuente: str  # clave del registro
    url_origen: str  # sin query string ni API key
    as_of: datetime  # UTC
    actividad: Actividad
    id_fiscal: str | None = None  # solo dígitos, sin DV
    tipo_titular: TipoTitular = "desconocido"
    ciudad: str | None = None
    direccion: str | None = None
    web: str | None = None


@dataclass(frozen=True)
class PaginaEmpresas:
    empresas: tuple[EmpresaCruda, ...]
    total: int | None  # lo que reporte la fuente


@dataclass(frozen=True)
class MetaFuente:  # sale de la entrada de fuentes.yaml, no de la clase
    clave: str
    proveedor: str
    paises: frozenset[str]  # "*" = cualquiera
    filtros: frozenset[str]
    trae: frozenset[str]
    tipo: Literal["dataset", "live"]
    licencia: str
    endpoint: str | None = None
    tipo_titular_implicito: TipoTitular | None = None


def cubre(meta: MetaFuente, criterios: CriteriosICP) -> bool:
    pais_ok = criterios.pais in meta.paises or "*" in meta.paises
    return pais_ok and set(criterios.filtros) <= meta.filtros
