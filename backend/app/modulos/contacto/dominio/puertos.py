from typing import Protocol
from uuid import UUID

from app.modulos.contacto.dominio.modelos import LeadContactable, MensajeSaliente, ResultadoEnvio


class CanalContacto(Protocol):
    canal: str

    def enviar(self, mensaje: MensajeSaliente) -> ResultadoEnvio:
        """Registra el costo antes de devolver o de lanzar. Transporte caído → CanalNoDisponible sin la dirección."""
        ...


class LeadsContactables(Protocol):
    def de_busqueda(self, busqueda_id: UUID, canal: str) -> list[LeadContactable]:
        """Solo jurídicas, contactables, con canal publicado y sin opt-out."""
        ...


class RepositorioContactos(Protocol):
    """Contactos de un tenant. La elegibilidad legal (jurídica, cumplimiento, sin opt-out) se decide en SQL."""

    def mensaje_base(self, busqueda_id: UUID) -> str | None: ...

    def aprobados(self, busqueda_id: UUID) -> list[tuple[UUID, UUID, str]]:
        """(contacto_id, lead_id, cuerpo) de los contactos en estado aprobado."""
        ...

    def crear(self, busqueda_id: UUID, contacto_id: UUID, lead_id: UUID, asunto: str, cuerpo: str) -> bool:
        """Crea el contacto aprobado solo si el lead es elegible; False si no lo es o ya tenía contacto."""
        ...

    def fijar_mensaje(self, contacto_id: UUID, asunto: str, cuerpo: str) -> None: ...

    def reclamar(self, contacto_id: UUID) -> bool:
        """aprobado → enviando y fija la base legal, en una transacción. False si otro lo reclamó o dejó de ser elegible."""
        ...

    def vigente(self, contacto_id: UUID) -> bool:
        """Sigue elegible y con base legal, justo antes de mandar."""
        ...

    def confirmar(self, contacto_id: UUID) -> None: ...

    def liberar(self, contacto_id: UUID) -> None: ...

    def descartar(self, contacto_id: UUID) -> None: ...

    def dar_de_baja(self, contacto_id: UUID, via: str) -> bool:
        """Opt-out del lead del contacto (todos los canales), monotónico, en una transacción. False si no existe."""
        ...
