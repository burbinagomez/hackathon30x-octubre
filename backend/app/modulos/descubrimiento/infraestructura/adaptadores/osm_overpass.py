import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.dominio.errores import CriterioNoSoportado, FuenteNoDisponible
from app.modulos.descubrimiento.dominio.modelos import (
    Actividad,
    CriteriosICP,
    EmpresaCruda,
    MetaFuente,
    PaginaEmpresas,
)

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
        reloj: Callable[[], float] = time.monotonic,
    ):
        self._reloj = reloj
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
        t0 = self._reloj()
        try:
            respuesta = self._http.post(self._url, data={"data": armar_query(criterios)})
        finally:
            # Por intento y antes de devolver o lanzar: solo los segundos del request.
            self._registrar_segundos(self._reloj() - t0)

        if respuesta.status_code != 200:
            # Solo el código: el cuerpo puede traer cualquier cosa del servidor.
            raise FuenteNoDisponible(f"osm_overpass http {respuesta.status_code}") from None
        try:
            cuerpo = respuesta.json()
            as_of = datetime.fromisoformat(cuerpo["osm3s"]["timestamp_osm_base"])
            empresas = tuple(
                e
                for el in cuerpo.get("elements", ())
                if (e := self._mapear(el, criterios, as_of)) is not None
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            raise FuenteNoDisponible("osm_overpass respuesta ilegible") from None
        return PaginaEmpresas(empresas, None)

    def _registrar_segundos(self, segundos: float) -> None:
        self._costos.registrar(
            OperacionCosto(
                tipo="overpass_query",
                unidades=Decimal(str(round(segundos, 3))),
                costo_unitario=self._costo_unitario,
                moneda="USD",
                proveedor="osm",
                fuente=self.meta.clave,
                canal=None,
                lead_id=None,
                lote_id=self._lote_id,
                gratis=False,  # el cómputo es nuestro aunque Overpass no cobre
            )
        )

    def _mapear(self, el: dict, criterios: CriteriosICP, as_of: datetime) -> EmpresaCruda | None:
        # En el [MIN] no se mapea contacto (teléfono, email, web): llega con T040p, cifrado.
        tags = el.get("tags") or {}
        nombre = (tags.get("name") or "").strip()
        if not nombre:
            return None
        etiquetas = criterios.filtros["tipo_negocio"]
        etiqueta = next((t for t in etiquetas if tags.get(t.partition("=")[0]) == t.partition("=")[2]), etiquetas[0])
        direccion = " ".join(p for p in (tags.get("addr:street"), tags.get("addr:housenumber")) if p) or None
        return EmpresaCruda(
            pais=criterios.pais,
            nombre=nombre,
            fuente=self.meta.clave,
            url_origen=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            as_of=as_of,
            actividad=Actividad(etiqueta, "OSM"),
            ciudad=tags.get("addr:city") or str(criterios.filtros["ciudad"]),
            direccion=direccion,
        )
