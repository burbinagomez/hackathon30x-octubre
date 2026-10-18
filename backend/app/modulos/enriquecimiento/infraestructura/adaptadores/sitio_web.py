from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.enriquecimiento.dominio.puertos import ContactoPublicado

Resolvedor = Callable[[str], list[str]]  # host -> IPs


class SitioWeb:
    def __init__(self, registro_costos: RegistroCostos, transporte: httpx.BaseTransport,
                 resolver: Resolvedor, costo_unitario: Decimal):
        self._costos = registro_costos
        self._transporte = transporte
        self._resolver = resolver
        self._costo_unitario = costo_unitario

    def enriquecer(self, lead_id: UUID, dominio: str) -> ContactoPublicado:
        return ContactoPublicado((), (), "ok")
