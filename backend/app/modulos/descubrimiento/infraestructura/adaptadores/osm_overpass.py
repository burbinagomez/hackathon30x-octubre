from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.dominio.errores import CriterioNoSoportado
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente, PaginaEmpresas

OVERPASS_URL = "https://overpass-api.de/api/interpreter"  # override: Settings.overpass_url
AGENTE = "dapta-reto-30x/0.1"
TOPE_ELEMENTOS = 500
TIMEOUT_HTTP_S = 30  # el [timeout:25] del servidor + margen


def _ql(valor: str) -> str:
    """Literal de Overpass QL entre comillas: el ICP no puede inyectar QL."""
    return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') + '"'


def armar_query(criterios: CriteriosICP) -> str:
    ramas = []
    for etiqueta in criterios.filtros["tipo_negocio"]:
        clave, _, valor = etiqueta.partition("=")
        ramas.append(f"  nwr(area.ciudad)[{_ql(clave)}={_ql(valor)}][\"name\"];")
    return "\n".join(
        [
            "[out:json][timeout:25];",
            f'area["ISO3166-1"={_ql(criterios.pais)}][admin_level=2]->.pais;',
            f'rel(area.pais)["name"={_ql(str(criterios.filtros["ciudad"]))}]["boundary"="administrative"];',
            "map_to_area->.ciudad;",
            "(",
            *ramas,
            ");",
            f"out center tags {TOPE_ELEMENTOS};",
        ]
    )


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
        self._http = httpx.Client(
            transport=transporte,
            timeout=TIMEOUT_HTTP_S,
            headers={"User-Agent": f"{AGENTE} (+{repo_url})"},
        )

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        sobrantes = set(criterios.filtros) - self.meta.filtros
        if sobrantes:
            raise CriterioNoSoportado(f"{self.meta.clave} no filtra por {sorted(sobrantes)}")
        self._http.post(self._url, data={"data": armar_query(criterios)})
        return PaginaEmpresas((), None)
