from decimal import Decimal
from uuid import UUID

import httpx
from pydantic import SecretStr

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.enriquecimiento.dominio.puertos import Encaje


class JevClasificador:
    def __init__(self, registro_costos: RegistroCostos, transporte: httpx.BaseTransport, url: str,
                 credencial: SecretStr, usd_in_por_M: Decimal):
        self._costos = registro_costos
        self._transporte = transporte
        self._url = url
        self._credencial = credencial
        self._usd_in_por_M = usd_in_por_M

    def clasificar(self, lead_id: UUID, descripcion_icp: str, nombre: str, ciudad: str | None,
                   actividad: str | None) -> Encaje:
        return Encaje("encaja", 1.0)
