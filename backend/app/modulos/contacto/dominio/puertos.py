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
