from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.aplicacion.camaras import Camara
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente, PaginaEmpresas

# Dataset público de Confecámaras en datos.gov.co. El override (stub, D9) llega desde settings por la fábrica.
URL_DATASET = "https://www.datos.gov.co/resource/c82u-588k.json"


class DatosGovCoRues:
    def __init__(
        self,
        *,
        transporte: httpx.BaseTransport,
        reloj: Callable[[], datetime],
        dormir: Callable[[float], None],
        costos: RegistroCostos,
        cache: Any | None,  # puerto de caché de la 002; None en el mínimo
        camaras: Mapping[str, Camara],
        tarifas: Mapping[str, Any],
        lote_id: UUID | None,
        meta: MetaFuente,
        url: str = URL_DATASET,
        app_token: str | None = None,
    ) -> None:
        self._transporte = transporte
        self._reloj = reloj
        self._dormir = dormir
        self._costos = costos
        self._cache = cache
        self._camaras = camaras
        self._tarifas = tarifas
        self._lote_id = lote_id
        self.meta = meta
        self._url = url
        self._app_token = app_token

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        return PaginaEmpresas(empresas=(), total=None)
