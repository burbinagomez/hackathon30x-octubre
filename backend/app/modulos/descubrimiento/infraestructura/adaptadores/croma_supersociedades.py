"""croma_supersociedades_co (T017): Supersociedades CO vía Croma. ESQUELETO: hace 0 requests y devuelve una página vacía,
para que los rojos de límites y de costo máximo fallen por aserción. El adaptador real llega después del visto bueno
del advisor al tope."""
from collections.abc import Mapping
from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente, PaginaEmpresas

CROMA_URL = "https://api.croma.run"  # override: Settings.croma_base_url (T020)


class CromaSupersociedadesCo:
    def __init__(self, meta: MetaFuente, registro_costos: RegistroCostos, transporte: httpx.BaseTransport,
                 costo_unitario: Decimal, lote_id: UUID, api_key: str, limites: Mapping, url: str = CROMA_URL):
        self.meta = meta
        self._costos = registro_costos

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        return PaginaEmpresas((), None)
