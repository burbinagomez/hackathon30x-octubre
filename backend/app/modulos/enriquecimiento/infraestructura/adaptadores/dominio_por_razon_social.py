"""dominio_por_razon_social: busca el sitio de un lead jurídico que no trae web, probando dominios armados con su razón
social. Un dominio se acepta SOLO si su página trae el NIT o la razón social completa (`verifica_pagina`).

Defensas (las de `sitio_web`): DNS primero (lo que no resuelve no recibe HTTP), SSRF validado en cada salto y conexión a la
IP validada, redirecciones solo dentro del dominio, 2 MB como tope, mismo User-Agent. Una sola página por candidato (la
portada): no se cruza robots.txt porque no se extrae contacto acá, solo se comprueba de quién es el sitio; el contacto lo
saca después `sitio_web`, que sí respeta robots. Cada request escribe `web_fetch` con `lead_id` antes de enviarse.
"""
import logging
import time
import zlib
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.dominio.modelos import EvidenciaSitioWeb
from app.modulos.enriquecimiento.dominio.dominios import candidatos_de_dominio, verifica_pagina
from app.modulos.enriquecimiento.dominio.errores import DemasiadasRedirecciones, IPPrivadaRechazada
from app.modulos.enriquecimiento.infraestructura.adaptadores.sitio_web import (
    MAX_REDIRECCIONES,
    Resolvedor,
    SitioWeb,
    _en_sitio_web,
    _host,
    _leer,
    _PlazoVencido,
    _RespuestaInvalida,
    _sin_www,
    validar_destino,
)

log = logging.getLogger(__name__)

TIMEOUT_S = 4.0  # por operación de socket
PLAZO_LEAD_S = 12.0  # todos los candidatos de un lead: seis dominios muertos no retienen al worker


class DominioPorRazonSocial:
    def __init__(self, registro_costos: RegistroCostos, transporte: httpx.BaseTransport, resolver: Resolvedor,
                 costo_unitario: Decimal, reloj: Callable[[], float] = time.monotonic, plazo_s: float = PLAZO_LEAD_S):
        self._costos = registro_costos
        self._transporte = transporte
        self._resolver = resolver
        self._costo_unitario = costo_unitario
        self._reloj = reloj
        self._plazo_s = plazo_s

    def buscar(self, lead_id: UUID, razon_social: str, nit: str | None) -> EvidenciaSitioWeb | None:
        limite = self._reloj() + self._plazo_s
        marca = _en_sitio_web.set(True)  # httpx en INFO loguea IP y ruta de cada salto
        try:
            for dominio in candidatos_de_dominio(razon_social):
                if self._reloj() > limite:
                    break
                motivo = self._probar(lead_id, dominio, razon_social, nit, limite)
                if motivo is not None:
                    return EvidenciaSitioWeb(dominio, f"https://{dominio}/", motivo)
        finally:
            _en_sitio_web.reset(marca)
        return None

    def _probar(self, lead_id: UUID, dominio: str, razon_social: str, nit: str | None, limite: float) -> str | None:
        try:
            ips = self._resolver(dominio)
        except (OSError, LookupError):
            return None  # no resuelve: se descarta sin HTTP
        try:
            pagina = self._obtener(lead_id, dominio, ips, limite)
        except (IPPrivadaRechazada, DemasiadasRedirecciones, _RespuestaInvalida, _PlazoVencido, httpx.HTTPError,
                httpx.InvalidURL, OSError, zlib.error) as e:
            log.info("dominio_por_razon_social descartado lead_id=%s motivo=%s", lead_id, type(e).__name__)  # nunca el dominio
            return None
        return verifica_pagina(pagina.decode("utf-8", errors="replace"), nit, razon_social)

    def _obtener(self, lead_id: UUID, dominio: str, ips: list[str], limite: float) -> bytes:
        actual = httpx.URL(f"https://{dominio}/")
        base = _sin_www(_host(actual))

        def chequear_plazo() -> None:
            if self._reloj() > limite:
                raise _PlazoVencido
        with httpx.Client(transport=self._transporte, trust_env=False, timeout=TIMEOUT_S) as cliente:
            for salto in range(MAX_REDIRECCIONES + 1):
                host = _host(actual)
                if actual.scheme not in ("http", "https") or not host or _sin_www(host) != base:
                    raise _RespuestaInvalida
                # El primer salto ya resolvió: se valida lo que ya se vio, no se vuelve a preguntar (anti-rebinding).
                ip = validar_destino(host, (lambda _h: ips) if salto == 0 else self._resolver)
                chequear_plazo()
                respuesta = self._pedir(cliente, lead_id, actual, ip)
                try:
                    if respuesta.has_redirect_location:
                        actual = actual.join(respuesta.headers["location"])
                        continue
                    if respuesta.status_code != 200:
                        raise _RespuestaInvalida
                    cuerpo, _ = _leer(respuesta, chequear_plazo)
                    return cuerpo
                finally:
                    respuesta.close()
        raise DemasiadasRedirecciones(dominio)

    def _pedir(self, cliente: httpx.Client, lead_id: UUID, url: httpx.URL, ip: str) -> httpx.Response:
        host = _host(url)
        pedido = cliente.build_request(
            "GET", url.copy_with(host=ip),
            headers={"Host": host, "User-Agent": SitioWeb.USER_AGENT, "Accept-Encoding": "identity"},
            extensions={"sni_hostname": host} if url.scheme == "https" else None)
        self._costos.registrar(OperacionCosto(  # sin pedido no hay fila; con pedido, la fila va antes de enviarlo
            tipo="web_fetch", unidades=Decimal(1), costo_unitario=self._costo_unitario, moneda="USD",
            proveedor="web", fuente=None, canal=None, lead_id=lead_id, lote_id=None, gratis=False))
        return cliente.send(pedido, stream=True)
