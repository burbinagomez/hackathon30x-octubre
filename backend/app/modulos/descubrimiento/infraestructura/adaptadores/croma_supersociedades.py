"""croma_supersociedades_co (T017): empresas que reportan a Supersociedades, vía Croma `companies-search`.

Todo lo que devuelve es persona jurídica. Cada request enviado deja su fila en `costos` ANTES de devolver o lanzar
(principio VIII): 1 crédito a valor de lista si Croma respondió 200, 0 si el intento falló. Los límites (requests/24 h y
cupo mensual de créditos) se miran antes de CADA request y, si no alcanzan, no se hace ninguno.

La forma de la respuesta (`data`, `total`, y los campos de cada empresa) es la de la documentación y de la fixture
sintética: se contrasta con la respuesta real en la corrida T048. La API key viaja solo en el header y nunca en
mensajes, logs ni repr.
"""
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.dominio.errores import CriterioNoSoportado, FuenteNoDisponible, LimiteFuenteAgotado
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda, MetaFuente, PaginaEmpresas
from app.modulos.descubrimiento.dominio.nit import normalizar_nit

CROMA_URL = "https://api.croma.run"  # override: Settings.croma_base_url
CREDITOS_DATASET = Decimal(1)  # tarifas.yaml: croma.creditos_dataset
POR_PAGINA = 100
TIMEOUT_SEG = 10.0
INTENTOS = 2  # un reintento con backoff ante 502, 503 o timeout
ESPERA_REINTENTO_SEG = 1.0
REINTENTABLES = frozenset({502, 503})
# filtro del ICP -> parámetro de Croma
PARAMETROS = {"ciiu": "ciiu_code", "departamento": "department", "macrosector": "macrosector", "region": "region",
              "ingresos_min": "min_revenue"}


class CromaSupersociedadesCo:
    def __init__(self, meta: MetaFuente, registro_costos: RegistroCostos, transporte: httpx.BaseTransport,
                 costo_unitario: Decimal, lote_id: UUID, api_key: str, limites: Mapping, url: str = CROMA_URL,
                 reloj: Callable[[], datetime] = lambda: datetime.now(UTC),
                 dormir: Callable[[float], None] = time.sleep):
        # Peor caso de UNA llamada: 1 crédito (los intentos fallidos registran 0), a valor de lista.
        self.meta = replace(meta, costo_maximo_llamada=CREDITOS_DATASET * costo_unitario)
        self._costos = registro_costos
        self._costo_unitario = costo_unitario
        self._lote_id = lote_id
        self._limites = limites
        self._url = url.rstrip("/")
        self._reloj = reloj
        self._dormir = dormir
        self._http = httpx.Client(transport=transporte, timeout=TIMEOUT_SEG,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def __repr__(self) -> str:  # sin la key, ni por accidente
        return f"CromaSupersociedadesCo(lote_id={self._lote_id})"

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        sobrantes = set(criterios.filtros) - self.meta.filtros
        if sobrantes:
            raise CriterioNoSoportado(f"{self.meta.clave} no filtra por {sorted(sobrantes)}")
        cuerpo = {"page": pagina, "per_page": POR_PAGINA}
        for filtro, valor in criterios.filtros.items():
            cuerpo[PARAMETROS[filtro]] = int(valor) if filtro == "ingresos_min" else valor

        respuesta = self._enviar(cuerpo)
        try:
            datos = respuesta.json()
            total = datos["total"]
            if type(total) is not int or not isinstance(datos["data"], list):
                raise TypeError
            as_of = self._reloj()
            empresas = tuple(e for item in datos["data"] if (e := self._mapear(item, criterios, as_of)) is not None)
        except (ValueError, KeyError, TypeError, AttributeError):
            # Croma ya cobró este 200: la fila quedó escrita en `_enviar`. Mensaje fijo, sin el cuerpo.
            raise FuenteNoDisponible(f"{self.meta.clave}: respuesta ilegible") from None
        return PaginaEmpresas(empresas, total)

    def _enviar(self, cuerpo: dict) -> httpx.Response:
        """Hasta INTENTOS requests. Antes de cada uno, los límites; después de cada uno, su fila de costos."""
        for intento in range(INTENTOS):
            self._exigir_cupo()
            try:
                respuesta = self._http.post(self._url + self.meta.endpoint, json=cuerpo)
            except httpx.TransportError:
                self._registrar(fallido=True)
                if intento + 1 == INTENTOS:
                    raise FuenteNoDisponible(f"{self.meta.clave}: sin respuesta") from None
                self._dormir(ESPERA_REINTENTO_SEG)
                continue
            codigo = respuesta.status_code
            if codigo == 200:
                self._registrar(fallido=False)  # Croma cobra el 200 aunque no se pueda leer
                return respuesta
            self._registrar(fallido=True)
            if codigo == 429:
                raise LimiteFuenteAgotado(f"{self.meta.clave}: http 429")
            if codigo in REINTENTABLES and intento + 1 < INTENTOS:
                self._dormir(ESPERA_REINTENTO_SEG)
                continue
            raise FuenteNoDisponible(f"{self.meta.clave}: http {codigo}")
        raise AssertionError("inalcanzable")  # pragma: no cover

    def _exigir_cupo(self) -> None:
        """Sin request si el límite de 24 h llegó, o si otro crédito pasaría el cupo gratis del mes (estricto)."""
        if self._costos.requests_24h("croma") >= self._limites["croma_requests_por_24h"]:
            raise LimiteFuenteAgotado(f"{self.meta.clave}: límite de requests en 24 h")
        if self._costos.creditos_mes("croma") + CREDITOS_DATASET > self._limites["croma_creditos_gratis_mes"]:
            raise LimiteFuenteAgotado(f"{self.meta.clave}: cupo mensual de créditos")

    def _registrar(self, *, fallido: bool) -> None:
        self._costos.registrar(OperacionCosto(
            tipo="croma_consulta",
            unidades=Decimal(0) if fallido else CREDITOS_DATASET,
            costo_unitario=Decimal(0) if fallido else self._costo_unitario,
            moneda="USD", proveedor="croma", fuente=self.meta.clave, canal=None, lead_id=None,
            lote_id=self._lote_id, gratis=True,  # dentro del cupo (se exige antes de enviar); el valor de lista queda en la fila
        ))

    def _mapear(self, item: dict, criterios: CriteriosICP, as_of: datetime) -> EmpresaCruda | None:
        nit = normalizar_nit(str(item.get("nit") or ""))
        nombre = (item.get("name") or "").strip()
        if not nit or not nombre:
            return None
        return EmpresaCruda(
            pais="CO", nombre=nombre, fuente=self.meta.clave,
            url_origen=f"{self._url}{self.meta.endpoint}?nit={nit}",  # sin la API key
            as_of=as_of, actividad=Actividad(str(item.get("ciiu_code") or criterios.filtros.get("ciiu") or ""), "CIIU"),
            id_fiscal=nit, tipo_titular="juridica",  # todo lo que reporta a Supersociedades es sociedad
            ciudad=item.get("city") or None, direccion=item.get("address") or None,
        )
