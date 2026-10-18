from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Literal, NamedTuple
from uuid import UUID


class Actividad(NamedTuple):  # NamedTuple: se compara con ("4711", "CIIU")
    codigo: str
    sistema: str  # "CIIU" | "SCIAN" | "CNAE"


TipoTitular = Literal["juridica", "natural", "desconocido"]


@dataclass(frozen=True)
class CriteriosICP:
    pais: str  # ISO 3166-1 alfa-2, mayúsculas
    filtros: Mapping[str, str | tuple[str, ...]]  # vocabulario de fuentes.yaml; tupla = varios valores


@dataclass(frozen=True)
class Borrador:
    """Una búsqueda guardada con estado `borrador`: criterios congelados y el formulario común."""
    id: UUID
    criterios: CriteriosICP
    canal_preferido: str | None
    tope_gasto_usd: Decimal
    mensaje_base: str | None


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
class Lead:
    """Un lead guardado, con nombre y dirección en claro: el repositorio descifra, el dominio nunca ve bytes."""
    id: UUID
    pais: str
    tipo_titular: TipoTitular
    nombre: str | None = None
    direccion: str | None = None
    id_fiscal: str | None = None
    ciudad: str | None = None
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
    # Cota alta de lo que puede costar UNA llamada a `buscar`, a valor de lista. La fija cada adaptador al armarse
    # (dataclasses.replace) con su tarifa; el tope de gasto la usa. 0 = "no declarado": la suite de contrato lo rechaza.
    costo_maximo_llamada: Decimal = Decimal("0")


def cubre(meta: MetaFuente, criterios: CriteriosICP) -> bool:
    return criterios.pais in meta.paises or "*" in meta.paises
