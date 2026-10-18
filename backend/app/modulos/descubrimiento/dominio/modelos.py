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


Contacto = tuple[str, str]  # (valor, canal publicado); el valor nunca sale de memoria sin cifrar


@dataclass(frozen=True)
class LeadParaEnriquecer:
    """Lo que el enriquecimiento necesita de un lead, descifrado por el repositorio."""
    id: UUID
    tipo_titular: TipoTitular
    nombre: str
    ciudad: str | None
    web: str | None
    actividad: str | None
    descripcion_icp: str | None  # de la búsqueda; None = no se clasifica
    telefono: Contacto | None = None
    email: Contacto | None = None


@dataclass(frozen=True)
class ResultadoEnriquecimiento:
    tipo_titular: TipoTitular
    telefono: Contacto | None
    email: Contacto | None
    contactable: bool
    razon_no_contactable: str | None
    encaje: str | None = None  # None = sin clasificar


@dataclass(frozen=True)
class ResumenBusqueda:
    id: UUID
    creada_en: datetime
    estado: str
    pais: str
    departamento: str | None
    ciudad: str | None
    total_leads: int


@dataclass(frozen=True)
class LeadListado:
    """Fila de la pantalla "Leads de la búsqueda". Sin dirección y sin valores de contacto: solo si existen.
    `nombre` es None salvo para una jurídica. `tiene_telefono`/`tiene_email`: bool solo para una jurídica; None para natural o desconocido (no se expone)."""
    id: UUID
    nombre: str | None
    tipo_titular: TipoTitular
    fuentes: tuple[str, ...]
    licencias: tuple[str, ...]
    ciudad: str | None
    tiene_web: bool
    tiene_telefono: bool | None = None
    tiene_email: bool | None = None


@dataclass(frozen=True)
class AtribucionFuente:
    fuente: str
    texto: str
    url: str


@dataclass(frozen=True)
class PaginaLeads:
    items: tuple[LeadListado, ...]
    total: int
    pagina: int
    tamano: int
    atribuciones: tuple[AtribucionFuente, ...]


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
