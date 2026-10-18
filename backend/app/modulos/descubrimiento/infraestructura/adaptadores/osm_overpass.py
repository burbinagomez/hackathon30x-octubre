from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente, PaginaEmpresas

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


class OsmOverpass:
    def __init__(
        self,
        meta: MetaFuente,
        registro_costos: RegistroCostos,
        transporte: httpx.BaseTransport,
        costo_unitario: Decimal,
        lote_id: UUID,
        repo_url: str,
        url: str = OVERPASS_URL,
    ):
        self.meta = meta
        self._costos = registro_costos
        self._costo_unitario = costo_unitario
        self._lote_id = lote_id
        self._url = url
        self._http = httpx.Client(transport=transporte)

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        self._http.post(self._url, data={"data": "[out:json];"})
        return PaginaEmpresas((), None)
