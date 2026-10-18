"""sitio_web: lee la página del lead y extrae el contacto publicado.

Defensas: SSRF validado en cada salto y conexión a la IP validada (anti-rebinding), robots.txt por host,
tope de 2 MB sobre bytes decodificados, 3 redirecciones como máximo y solo dentro del dominio del lead.
"""
import ipaddress
import logging
import re
import time
import zlib
from collections.abc import Callable
from decimal import Decimal
from urllib.robotparser import RobotFileParser
from uuid import UUID

import httpx

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.enriquecimiento.dominio.canal import CONFIANZA_CANAL, CanalPublicado
from app.modulos.enriquecimiento.dominio.errores import DemasiadasRedirecciones, IPPrivadaRechazada
from app.modulos.enriquecimiento.dominio.puertos import ContactoPublicado

log = logging.getLogger(__name__)

Resolvedor = Callable[[str], list[str]]  # host -> IPs

LIMITE_BYTES = 2 * 1024 * 1024
MAX_REDIRECCIONES = 3
TIMEOUT_S = 5.0  # por operación de socket
PLAZO_TOTAL_S = 20.0  # por lead: robots + saltos + lectura; un goteo lento no retiene al worker

_MAILTO = re.compile(r"mailto:([^\"'?<>\s@]{1,64}@[^\"'?<>\s@]{1,255})", re.I)  # acotada: sin tope era O(n²)
_WA_ME = re.compile(r"wa\.me/(\d{8,15})")
_TELEFONO = re.compile(r"(?<!\d)(?:\+57[\s-]?)?(?:3\d{2}|60\d)[\s-]?\d{3}[\s-]?\d{4}")


class _BloqueadoPorRobots(Exception):
    pass


class _PlazoVencido(Exception):
    pass


class _RespuestaInvalida(Exception):
    """Location sin http/https o sin host, salto fuera del dominio, estado final no 200 o codificación rara."""


def validar_destino(host: str, resolver: Resolvedor) -> str:
    ips = resolver(host)
    if not ips:
        raise IPPrivadaRechazada(host)
    for crudo in ips:
        try:
            ip = ipaddress.ip_address(crudo)
        except ValueError:
            raise IPPrivadaRechazada(host) from None
        if not ip.is_global or ip.is_multicast:  # is_private no cubre 100.64/10; is_global deja pasar multicast
            raise IPPrivadaRechazada(host)
    return ips[0]


def _host(url: httpx.URL) -> str:
    return url.raw_host.decode("ascii")  # punycode: unicode no entra en Host/SNI ni en el resolvedor


def _sin_www(host: str) -> str:
    return host.removeprefix("www.")


class SitioWeb:
    USER_AGENT = "Mozilla/5.0 (compatible; EnriquecedorBot/1.0)"
    TOKEN_ROBOTS = "EnriquecedorBot"  # RobotFileParser corta el UA en el primer "/": con USER_AGENT compararía "mozilla"

    def __init__(self, registro_costos: RegistroCostos, transporte: httpx.BaseTransport,
                 resolver: Resolvedor, costo_unitario: Decimal, reloj: Callable[[], float] = time.monotonic):
        self._costos = registro_costos
        self._transporte = transporte
        self._resolver = resolver
        self._costo_unitario = costo_unitario
        self._reloj = reloj

    def enriquecer(self, lead_id: UUID, dominio: str) -> ContactoPublicado:
        try:
            cuerpo, truncado = self.obtener(lead_id, f"https://{dominio}/")
        except _BloqueadoPorRobots:
            return ContactoPublicado((), (), "fetch_bloqueado_por_robots")
        except (IPPrivadaRechazada, DemasiadasRedirecciones, _RespuestaInvalida, _PlazoVencido, httpx.HTTPError, httpx.InvalidURL, OSError,
                zlib.error, KeyError) as e:
            log.info("sitio_web fallo lead_id=%s motivo=%s", lead_id, type(e).__name__)  # nunca el contenido
            return ContactoPublicado((), (), "fallo")
        emails, telefonos = _extraer(cuerpo.decode("utf-8", errors="replace"))
        return ContactoPublicado(emails, telefonos, "truncado" if truncado else "ok")

    def obtener(self, lead_id: UUID, url: str) -> tuple[bytes, bool]:
        actual = httpx.URL(url)
        base = _sin_www(_host(actual))
        robots_ok: set[str] = set()
        limite = self._reloj() + PLAZO_TOTAL_S

        def chequear_plazo() -> None:
            if self._reloj() > limite:
                raise _PlazoVencido
        with httpx.Client(transport=self._transporte, trust_env=False, timeout=TIMEOUT_S) as cliente:
            for _ in range(MAX_REDIRECCIONES + 1):
                chequear_plazo()
                host = _host(actual)
                if actual.scheme not in ("http", "https") or not host or _sin_www(host) != base:
                    raise _RespuestaInvalida
                ip = validar_destino(host, self._resolver)  # en cada salto, antes de cualquier request
                if host not in robots_ok:
                    self._chequear_robots(cliente, lead_id, actual, ip, chequear_plazo)
                    robots_ok.add(host)
                respuesta = self._pedir(cliente, lead_id, actual, ip)
                try:
                    if respuesta.has_redirect_location:
                        actual = actual.join(respuesta.headers["location"])
                        continue
                    if respuesta.status_code != 200:
                        raise _RespuestaInvalida
                    return _leer(respuesta, chequear_plazo)
                finally:
                    respuesta.close()
        raise DemasiadasRedirecciones(url)

    def _chequear_robots(self, cliente: httpx.Client, lead_id: UUID, url: httpx.URL, ip: str,
                         chequear_plazo: Callable[[], None]) -> None:
        respuesta = self._pedir(cliente, lead_id, url.copy_with(path="/robots.txt", query=None, fragment=None), ip)
        try:
            if respuesta.status_code >= 500:
                raise _BloqueadoPorRobots  # RFC 9309: servidor caído = todo prohibido
            if respuesta.status_code != 200:
                return  # 3xx/4xx: sin reglas
            texto, _ = _leer(respuesta, chequear_plazo)
        finally:
            respuesta.close()
        reglas = RobotFileParser()
        reglas.parse(texto.decode("utf-8", errors="replace").splitlines())
        if not reglas.can_fetch(self.TOKEN_ROBOTS, str(url)):
            raise _BloqueadoPorRobots

    def _pedir(self, cliente: httpx.Client, lead_id: UUID, url: httpx.URL, ip: str) -> httpx.Response:
        host = _host(url)
        pedido = cliente.build_request(
            "GET", url.copy_with(host=ip),
            headers={"Host": host, "User-Agent": self.USER_AGENT, "Accept-Encoding": "identity"},
            extensions={"sni_hostname": host} if url.scheme == "https" else None)
        self._costos.registrar(OperacionCosto(  # después de armar el pedido: sin pedido no hay fila
            tipo="web_fetch", unidades=Decimal(1), costo_unitario=self._costo_unitario, moneda="USD",
            proveedor="web", fuente=None, canal=None, lead_id=lead_id, lote_id=None, gratis=False))
        return cliente.send(pedido, stream=True)


def _leer(respuesta: httpx.Response, chequear_plazo: Callable[[], None]) -> tuple[bytes, bool]:
    """Lee hasta LIMITE_BYTES decodificados. Descomprime a mano con max_length: una bomba gzip no infla la memoria."""
    codificacion = respuesta.headers.get("content-encoding", "identity").lower()
    if codificacion not in ("identity", "gzip", "x-gzip", "deflate"):
        raise _RespuestaInvalida
    descompresor = None if codificacion == "identity" else zlib.decompressobj(47)  # 47 = gzip o zlib, autodetecta
    leido = bytearray()
    for crudo in respuesta.stream:  # crudo, sin decodificar; iter_raw rechaza respuestas ya leídas
        chequear_plazo()
        while crudo:
            if descompresor:
                trozo = descompresor.decompress(crudo, LIMITE_BYTES + 1 - len(leido))
                crudo = descompresor.unconsumed_tail
            else:
                trozo, crudo = crudo, b""
            leido += trozo
            if len(leido) > LIMITE_BYTES:
                return bytes(leido[:LIMITE_BYTES]), True
    return bytes(leido), False


def _extraer(html: str) -> tuple[tuple[str, ...], tuple[tuple[str, CanalPublicado], ...]]:
    emails = tuple(dict.fromkeys(m.lower() for m in _MAILTO.findall(html)))
    candidatos: list[tuple[str, CanalPublicado]] = [(n, "whatsapp_comercial") for n in _WA_ME.findall(html)]
    for m in _TELEFONO.findall(html):
        digitos = re.sub(r"\D", "", m)
        candidatos.append((f"57{digitos}" if len(digitos) == 10 else digitos, "sitio_web"))
    mejor: dict[str, tuple[str, CanalPublicado]] = {}
    for numero, canal in sorted(candidatos, key=lambda c: -CONFIANZA_CANAL[c[1]]):  # sort estable
        mejor.setdefault(numero, (numero, canal))
    return emails, tuple(mejor.values())
