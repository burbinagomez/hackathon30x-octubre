from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from app.modulos.enriquecimiento.dominio.canal import CanalPublicado


@dataclass(frozen=True)
class ContactoPublicado:
    emails: tuple[str, ...]
    telefonos: tuple[tuple[str, CanalPublicado], ...]  # (valor, canal); el valor nunca sale de memoria sin cifrar
    estado: Literal["ok", "sin_sitio", "fetch_bloqueado_por_robots", "truncado", "fallo"]


@dataclass(frozen=True)
class VerificacionTitular:
    tipo_titular: Literal["juridica", "desconocido"]
    motivo: Literal["match_unico", "sin_match", "ambiguo", "matricula_inactiva"]  # va al log de la corrida, no al lead


@dataclass(frozen=True)
class Encaje:
    etiqueta: Literal["encaja", "no_encaja", "ninguna"]
    probabilidad: float


class EnriquecedorContacto(Protocol):  # sitio_web
    def enriquecer(self, lead_id: UUID, dominio: str) -> ContactoPublicado: ...


class VerificadorTitular(Protocol):  # croma_rues_co
    def verificar(self, lead_id: UUID, nombre_normalizado: str, ciudad: str | None) -> VerificacionTitular: ...


class ClasificadorEncaje(Protocol):  # jev
    def clasificar(self, lead_id: UUID, descripcion_icp: str, nombre: str, ciudad: str | None,
                   actividad: str | None) -> Encaje: ...
