import contextvars
import logging
import re
import time
from dataclasses import dataclass, replace
from collections.abc import Callable, Collection, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import UUID

import httpx

from app.modulos.costos.dominio.modelos import ContextoCosto, OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.aplicacion.camaras import Camara, camaras_de
from app.modulos.descubrimiento.dominio.errores import (
    CriterioNoSoportado,
    FuenteNoDisponible,
)
from app.modulos.descubrimiento.dominio.modelos import (
    Actividad,
    CriteriosICP,
    EmpresaCruda,
    MetaFuente,
    PaginaEmpresas,
)

# httpx en INFO loguea la URL completa de cada request, y la de una búsqueda por razón social lleva el nombre del lead.
# Se calla solo dentro de `_pedir`: un setLevel global callaría al resto de la app.
_en_pedido = contextvars.ContextVar("datos_gov_co_en_pedido", default=False)
logging.getLogger("httpx").addFilter(lambda _registro: not _en_pedido.get())

# Dataset público de Confecámaras en datos.gov.co. El override (stub, D9) llega desde settings por la fábrica.
URL_DATASET = "https://www.datos.gov.co/resource/c82u-588k.json"

LIMITE_FILAS = 5000
TIMEOUT_SEG = 30.0
INTENTOS = 2
ESPERA_REINTENTO_SEG = 1.0
REINTENTABLES = frozenset({502, 503, 504, "timeout", "ConnectError"})
# Lista blanca: nunca se piden nombres, apellidos ni representante legal (principio VII).
SELECT_FILAS = (
    "nit,digito_verificacion,razon_social,cod_ciiu_act_econ_pri,"
    "codigo_camara,organizacion_juridica,fecha_renovacion"
)
# Para buscar por razón social: lo mismo más el estado de la matrícula. Sigue sin representante legal ni personas.
SELECT_COINCIDENCIAS = SELECT_FILAS + ",estado_matricula"
LIMITE_COINCIDENCIAS = 100
# [0-9] y no \d: \d acepta dígitos de otros alfabetos y esos no entran al SoQL ni al NIT.
_CIIU = re.compile(r"[0-9]{4}")
_NIT = re.compile(r"[89][0-9]{8}")
_CAMARA = re.compile(r"[0-9]{1,3}")


def _es_juridica_valida(fila: Mapping[str, Any]) -> bool:
    """Defensa en profundidad: el servidor ya filtró; acá se descarta lo que no debió llegar."""
    organizacion = fila.get("organizacion_juridica")
    nit = fila.get("nit")
    nombre = fila.get("razon_social")
    return (
        isinstance(organizacion, str)
        and organizacion.strip() != ""
        and organizacion.strip().upper() != "PERSONA NATURAL"
        and isinstance(nit, str)
        and _NIT.fullmatch(nit.strip()) is not None
        and isinstance(nombre, str)
        and nombre.strip() != ""
    )


@dataclass(frozen=True)
class CoincidenciaRazonSocial:
    nit: str
    ciiu: str | None
    camara: str | None
    estado_matricula: str | None
    razon_social: str | None = None
    organizacion_juridica: str | None = None


@dataclass(frozen=True)
class BusquedaRazonSocial:
    coincidencias: list[CoincidenciaRazonSocial]
    truncada: bool  # el servidor devolvió el tope de filas: pudo haber más candidatos que los traídos


def _literal_like(nombre: str) -> str:
    """Texto del usuario -> contenido seguro de un literal SoQL con LIKE: comillas duplicadas; sin comodines ni control."""
    limpio = "".join(c for c in nombre if c.isprintable() and c not in "%_\\")
    return " ".join(limpio.upper().split()).replace("'", "''")


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
        monotonico: Callable[[], float] = time.monotonic,
        timeout_seg: float = TIMEOUT_SEG,
        intentos: int = INTENTOS,
    ) -> None:
        self._timeout_seg = timeout_seg  # el descubrimiento espera 30 s; verificar un lead no puede retener al worker
        self._intentos = intentos
        self._transporte = transporte
        self._reloj = reloj  # hora de pared: solo para el as_of
        self._monotonico = (
            monotonico  # duración cobrada: no salta con el reloj de pared
        )
        self._dormir = dormir
        self._costos = costos
        self._cache = cache
        self._camaras = camaras
        self._tarifas = tarifas
        self._lote_id = lote_id
        # Peor caso de una búsqueda: 2 requests (filas y conteo de naturales) x 2 intentos x 30 s de cómputo.
        self.meta = replace(meta, costo_maximo_llamada=2 * INTENTOS * Decimal(str(TIMEOUT_SEG))
                            * Decimal(str(tarifas["computo_seg_usd"])))
        self._url = url
        self._app_token = app_token

    def _validar(self, criterios: CriteriosICP) -> tuple[str, list[str]]:
        ciiu = criterios.filtros.get("ciiu")
        if not isinstance(ciiu, str) or _CIIU.fullmatch(ciiu) is None:
            raise CriterioNoSoportado(f"{self.meta.clave}: ciiu debe ser de 4 dígitos")
        departamento = criterios.filtros.get("departamento")
        codigos = sorted(camaras_de(dict(self._camaras), departamento))
        if not codigos:
            raise CriterioNoSoportado(f"{self.meta.clave}: departamento sin cámaras")
        return ciiu, codigos

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        ciiu, codigos = self._validar(criterios)
        if pagina > 1:  # una sola página: sin $order no hay $offset estable
            return PaginaEmpresas(empresas=(), total=None)
        enlista = ",".join(
            f"'{c}'" for c in codigos
        )  # códigos del YAML, nunca texto libre
        where = (
            "organizacion_juridica != 'PERSONA NATURAL'"
            " AND organizacion_juridica IS NOT NULL"
            " AND estado_matricula = 'ACTIVA'"
            f" AND cod_ciiu_act_econ_pri = '{ciiu}'"
            f" AND codigo_camara in({enlista})"
            " AND nit IS NOT NULL"
        )
        respuesta = self._pedir(
            {"$select": SELECT_FILAS, "$where": where, "$limit": str(LIMITE_FILAS)}
        )
        as_of = self._as_of(respuesta)
        try:
            empresas = tuple(
                EmpresaCruda(
                    pais="CO",
                    nombre=fila["razon_social"].strip(),
                    fuente=self.meta.clave,
                    url_origen=f"{self._url}?nit={fila['nit'].strip()}",
                    as_of=as_of,
                    actividad=Actividad(ciiu, "CIIU"),
                    id_fiscal=fila["nit"].strip(),  # sin DV
                    tipo_titular="juridica",  # solo para filas que pasan _es_juridica_valida
                    ciudad=self._ciudad(fila.get("codigo_camara")),
                )
                for fila in respuesta.json()
                if _es_juridica_valida(fila)
            )
        except (ValueError, TypeError, AttributeError, KeyError):
            # El cuerpo puede traer cualquier cosa: el mensaje lleva solo la clave.
            raise FuenteNoDisponible(f"{self.meta.clave}: respuesta ilegible") from None
        return PaginaEmpresas(empresas=empresas, total=None)

    def buscar_coincidencias(
        self, nombre_normalizado: str, contexto_costo: ContextoCosto
    ) -> list[CoincidenciaRazonSocial]:
        return self.buscar_homonimas(nombre_normalizado, contexto_costo).coincidencias

    def buscar_homonimas(self, nombre_normalizado: str, contexto_costo: ContextoCosto) -> BusquedaRazonSocial:
        """Todas las jurídicas activas cuya razón social contiene el nombre (Puerta A de la 010 y verificación de titular
        de la 006).

        El costo de cada request se atribuye al contexto: `fuente='intake'` y el `lote_id` de la corrida, o el `lead_id`
        que se verifica; nunca a una búsqueda.
        """
        nombre = _literal_like(nombre_normalizado)
        if not nombre:
            return BusquedaRazonSocial([], False)
        where = (
            f"upper(razon_social) like '%{nombre}%'"
            " AND organizacion_juridica != 'PERSONA NATURAL'"
            " AND organizacion_juridica IS NOT NULL"
            " AND estado_matricula = 'ACTIVA'"
            " AND nit IS NOT NULL"
        )
        respuesta = self._pedir(
            {"$select": SELECT_COINCIDENCIAS, "$where": where, "$limit": str(LIMITE_COINCIDENCIAS)},
            contexto_costo,
        )
        try:
            filas = respuesta.json()
            coincidencias = [
                CoincidenciaRazonSocial(
                    nit=fila["nit"].strip(),
                    ciiu=fila.get("cod_ciiu_act_econ_pri"),
                    camara=None if fila.get("codigo_camara") is None else str(fila["codigo_camara"]),
                    estado_matricula=fila.get("estado_matricula"),
                    razon_social=fila.get("razon_social"),
                    organizacion_juridica=fila.get("organizacion_juridica"),
                )
                for fila in filas
                if _es_juridica_valida(fila)
            ]
            # Sobre las filas crudas: las que el cliente descarta por inválidas también cuentan contra el tope del servidor.
            return BusquedaRazonSocial(coincidencias, len(filas) >= LIMITE_COINCIDENCIAS)
        except (ValueError, TypeError, AttributeError, KeyError):
            raise FuenteNoDisponible(f"{self.meta.clave}: respuesta ilegible") from None

    def contar_naturales(self, nombre_normalizado: str, camaras: Collection[str], contexto_costo: ContextoCosto) -> int:
        """Cuántas personas naturales matriculadas tienen una razón social que contiene el nombre, en esas cámaras.

        Solo un `count(*)`: ningún nombre de persona sale del servidor (principio VII). Sirve para no ascender a jurídica
        un lead que también podría ser la persona natural homónima. Escribe su costo como cualquier request.
        """
        nombre = _literal_like(nombre_normalizado)
        # Códigos de cámara de 1 a 3 dígitos: lo que venga de fuera de ese formato no entra al SoQL.
        codigos = sorted({str(c) for c in camaras if _CAMARA.fullmatch(str(c))})
        if not nombre or not codigos:
            return 0
        enlista = ",".join(f"'{c}'" for c in codigos)
        where = (
            f"upper(razon_social) like '%{nombre}%'"
            " AND organizacion_juridica = 'PERSONA NATURAL'"
            f" AND codigo_camara in({enlista})"
        )
        respuesta = self._pedir({"$select": "count(*)", "$where": where}, contexto_costo)
        try:
            (fila,) = respuesta.json()
            cuenta = int(fila["count"])
            if cuenta < 0:
                raise ValueError
        except (ValueError, TypeError, AttributeError, KeyError):
            raise FuenteNoDisponible(f"{self.meta.clave}: respuesta ilegible") from None
        return cuenta

    def _pedir(self, params: Mapping[str, str], contexto: ContextoCosto | None = None) -> httpx.Response:
        """GET con hasta 2 intentos. Cada intento deja su fila en costos antes de decidir."""
        cabeceras = {"X-App-Token": self._app_token} if self._app_token else {}
        marca = _en_pedido.set(True)
        try:
            return self._pedir_con_reintentos(params, contexto, cabeceras)
        finally:
            _en_pedido.reset(marca)

    def _pedir_con_reintentos(self, params: Mapping[str, str], contexto: ContextoCosto | None,
                              cabeceras: Mapping[str, str]) -> httpx.Response:
        estado: int | str = "timeout"
        with httpx.Client(
            transport=self._transporte, timeout=self._timeout_seg, headers=cabeceras
        ) as cliente:
            for intento in range(self._intentos):
                if intento:
                    self._dormir(ESPERA_REINTENTO_SEG)  # la espera no se cobra
                inicio = self._monotonico()
                respuesta = None
                try:
                    respuesta = cliente.get(self._url, params=params)
                    estado = respuesta.status_code
                except httpx.TimeoutException:
                    estado = "timeout"
                except httpx.ConnectError:
                    estado = "ConnectError"
                except httpx.TransportError as error:
                    # No reintentable: solo el nombre del error, nunca su texto.
                    raise FuenteNoDisponible(
                        f"{self.meta.clave}: {type(error).__name__}"
                    ) from None
                finally:
                    # Por intento y antes de decidir o lanzar: solo los segundos del request.
                    self._registrar_costo(self._monotonico() - inicio, contexto)
                if respuesta is not None and respuesta.status_code == 200:
                    return respuesta
                if estado not in REINTENTABLES:
                    break
        # Solo el status: el cuerpo de la respuesta no sale en el mensaje.
        raise FuenteNoDisponible(f"{self.meta.clave}: {estado}") from None

    def _registrar_costo(self, segundos: float, contexto: ContextoCosto | None = None) -> None:
        self._costos.registrar(
            OperacionCosto(
                tipo="socrata_descarga",
                unidades=Decimal(str(segundos)),
                costo_unitario=Decimal(str(self._tarifas["computo_seg_usd"])),
                moneda="USD",
                proveedor=self.meta.proveedor,
                fuente=self.meta.clave if contexto is None else contexto.fuente,
                canal=None,
                lead_id=None if contexto is None else contexto.lead_id,
                lote_id=self._lote_id if contexto is None else contexto.lote_id,
                gratis=False,
            )
        )

    def _as_of(self, respuesta: httpx.Response) -> datetime:
        """Última modificación del dataset según SODA; sin header, la hora de la consulta."""
        valor = respuesta.headers.get("X-SODA2-Truth-Last-Modified")
        if valor:
            try:
                return parsedate_to_datetime(valor).astimezone(UTC)
            except (TypeError, ValueError):
                pass
        return self._reloj()

    def _ciudad(self, codigo: Any) -> str | None:
        camara = self._camaras.get(str(codigo))
        return camara.municipio_sede if camara else None
