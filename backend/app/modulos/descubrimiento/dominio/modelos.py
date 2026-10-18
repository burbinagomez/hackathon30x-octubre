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
    encaje: str | None = None  # 'encaja' | 'no_encaja' | 'ninguna'; None = sin clasificar o no jurídica


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
    pais: str  # el verificador de titular solo cubre CO
    telefono: Contacto | None = None
    email: Contacto | None = None
    id_fiscal: str | None = None  # NIT sin dígito de verificación; el buscador de sitio web lo usa para verificar


@dataclass(frozen=True)
class ConstanciaTitular:
    """Evidencia de una verificación de titular contra un registro público, para `cumplimiento.solicitudes`.
    Datos de la empresa (NIT, razón social, cámara, organización y estado de la matrícula), nunca contacto ni el nombre con que llegó el lead."""
    motivo: str
    fuente: str
    dataset: str
    nit: str | None = None
    razon_social: str | None = None
    municipio_sede_camara: str | None = None  # el RUES no trae municipio: es la sede de la cámara de la matrícula
    codigo_camara: str | None = None
    organizacion_juridica: str | None = None
    estado_matricula: str | None = None
    candidatos: int | None = None  # solo si fue ambiguo: cuántos NIT cumplían
    naturales_homonimas: int | None = None  # solo si una persona natural con ese nombre vuelve ambiguo el match


@dataclass(frozen=True)
class ResultadoEnriquecimiento:
    tipo_titular: TipoTitular
    telefono: Contacto | None
    email: Contacto | None
    contactable: bool
    razon_no_contactable: str | None
    encaje: str | None = None  # None = sin clasificar
    constancia_titular: ConstanciaTitular | None = None  # None = no se verificó (el titular ya venía del registro)
    web: str | None = None  # dominio hallado por el buscador de sitio web; None = el lead conserva la que tenía
    evidencia_web: "EvidenciaSitioWeb | None" = None  # su evidencia, para `cumplimiento`


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
    """Fila de la pantalla "Leads de la búsqueda". Sin dirección; el contacto solo de una jurídica.
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
    # Valores de contacto, solo de una jurídica (canal que la empresa publica); natural o desconocido: siempre None.
    telefono: str | None = None
    email: str | None = None
    web: str | None = None
    encaje: str | None = None  # 'encaja' | 'no_encaja' | 'ninguna'; None = sin clasificar o no jurídica


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


@dataclass(frozen=True)
class EvidenciaSitioWeb:
    """Por qué se aceptó el sitio de un lead (006, buscador de sitio web): dónde se verificó y con qué.
    Es la evidencia para `cumplimiento.solicitudes`: url de la empresa y motivo (`nit` | `razon_social`), nunca contacto."""
    dominio: str
    url: str
    motivo: str
