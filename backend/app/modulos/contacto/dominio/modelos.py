from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class LeadContactable:
    lead_id: UUID
    canal_origen: str  # 'sitio_web' | 'osm_contacto': lo cita el pie del mensaje
    direccion: str = field(repr=False)  # nunca en repr, logs ni excepciones


@dataclass(frozen=True)
class MensajeSaliente:
    contacto_id: UUID
    lead_id: UUID
    busqueda_id: UUID
    asunto: str
    cuerpo: str
    url_baja: str
    direccion: str = field(repr=False)


@dataclass(frozen=True)
class ResultadoEnvio:
    enviado: bool
