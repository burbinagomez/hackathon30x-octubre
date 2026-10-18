"""sitio_web: SSRF por salto, robots.txt, 2 MB, 3 redirecciones, extracción y costos. Sin red: MockTransport + DNS falso."""
import gzip
import logging
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.modulos.enriquecimiento.dominio.errores import DemasiadasRedirecciones, IPPrivadaRechazada
from app.modulos.enriquecimiento.infraestructura.adaptadores.sitio_web import SitioWeb, validar_destino
from tests.falsos import RegistroCostosFalso

PUBLICA = "93.184.216.34"
TARIFA = Decimal("0.00001")
MB = 1024 * 1024
CHUNK = 64 * 1024


class Red:
    """Rutea por Host + path (el adaptador conecta a la IP) y anota cada request que llega al transport."""

    def __init__(self, rutas: dict):
        self.rutas = {"empresa.co/robots.txt": httpx.Response(404), **rutas}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        r = self.rutas.get(f"{request.headers['host']}{request.url.path}", httpx.Response(404))
        return r() if callable(r) else r

    def paths(self) -> list[str]:
        return [f"{r.headers['host']}{r.url.path}" for r in self.requests]


class Dns:
    def __init__(self, tabla: dict[str, list[str]]):
        self.tabla = tabla

    def __call__(self, host: str) -> list[str]:
        return self.tabla[host]


def _sitio(red: Red, dns: dict | None = None, **kw) -> tuple[SitioWeb, RegistroCostosFalso]:
    costos = RegistroCostosFalso()
    tabla = {"empresa.co": [PUBLICA], **(dns or {})}
    return SitioWeb(costos, httpx.MockTransport(red), Dns(tabla), TARIFA, **kw), costos


def _html(cuerpo: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<html><body>{cuerpo}</body></html>")


# --- SSRF -------------------------------------------------------------------------------------------

PRIVADAS = ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "192.168.0.5",
            "100.64.0.1", "0.0.0.0", "224.0.0.1", "fe80::1", "fc00::1"]


@pytest.mark.parametrize("ip", PRIVADAS)
def test_validar_destino_lanza_ip_privada(ip):
    with pytest.raises(IPPrivadaRechazada):
        validar_destino("empresa.co", Dns({"empresa.co": [ip]}))


def test_validar_destino_rechaza_si_cualquiera_es_privada():
    with pytest.raises(IPPrivadaRechazada):
        validar_destino("empresa.co", Dns({"empresa.co": [PUBLICA, "10.0.0.1"]}))


def test_validar_destino_rechaza_resolucion_vacia():
    with pytest.raises(IPPrivadaRechazada):  # any([]) es False: sin esta guarda pasaría
        validar_destino("empresa.co", Dns({"empresa.co": []}))


def test_validar_destino_devuelve_la_ip_publica():
    assert validar_destino("empresa.co", Dns({"empresa.co": [PUBLICA]})) == PUBLICA


@pytest.mark.parametrize("ips", [["127.0.0.1"], ["10.9.9.9"], ["169.254.169.254"], ["::1"], []])
def test_rechaza_ip_privada(ips, caplog):
    red = Red({"empresa.co/": _html('<a href="mailto:contacto@empresa.co">x</a>')})
    sitio, costos = _sitio(red, {"empresa.co": ips})
    caplog.set_level(logging.DEBUG)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert resultado.emails == () and resultado.telefonos == ()
    assert red.requests == []  # ni robots.txt
    assert costos.filas == []  # P9: sin request no hay costo
    assert "IPPrivadaRechazada" in caplog.text  # el motivo va al log de la corrida


def test_redireccion_a_localhost_se_corta_antes_del_segundo_request():
    red = Red({"empresa.co/": httpx.Response(302, headers={"location": "http://localhost/admin"})})
    sitio, costos = _sitio(red, {"localhost": ["127.0.0.1"]})

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert red.paths() == ["empresa.co/robots.txt", "empresa.co/"]
    assert len(costos.filas) == 2


@pytest.mark.parametrize("location", ["file:///etc/passwd", "javascript:alert(1)", "http:///sin-host", "ftp://empresa.co/x"])
def test_redireccion_a_esquema_no_http_se_corta(location):
    red = Red({"empresa.co/": httpx.Response(302, headers={"location": location})})
    sitio, costos = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert red.paths() == ["empresa.co/robots.txt", "empresa.co/"]
    assert len(costos.filas) == 2


@pytest.mark.parametrize("location", ["https://www.facebook.com/empresa", "https://notempresa.co/"])
def test_redireccion_fuera_del_dominio_del_lead_se_corta(location):
    """spec.md:31: sitio_web solo sigue el dominio del lead (y nunca entra a los prohibidos)."""
    red = Red({"empresa.co/": httpx.Response(302, headers={"location": location})})
    sitio, costos = _sitio(red, {"www.facebook.com": [PUBLICA], "notempresa.co": [PUBLICA]})

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert red.paths() == ["empresa.co/robots.txt", "empresa.co/"]


def test_redireccion_a_www_privado_se_corta_por_ssrf(caplog):
    """El salto está dentro del dominio, así que solo lo frena la validación SSRF del salto."""
    red = Red({"empresa.co/": httpx.Response(301, headers={"location": "https://www.empresa.co/"})})
    sitio, costos = _sitio(red, {"www.empresa.co": ["10.0.0.7"]})
    caplog.set_level(logging.DEBUG)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert red.paths() == ["empresa.co/robots.txt", "empresa.co/"]  # ni el robots de www
    assert len(costos.filas) == 2
    assert "IPPrivadaRechazada" in caplog.text


def test_redireccion_a_www_se_sigue_con_su_robots():
    red = Red({
        "empresa.co/": httpx.Response(301, headers={"location": "https://www.empresa.co/"}),
        "www.empresa.co/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /\n"),
        "www.empresa.co/": _html('<a href="mailto:contacto@empresa.co">x</a>'),
    })
    sitio, _ = _sitio(red, {"www.empresa.co": ["151.101.1.1"]})

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fetch_bloqueado_por_robots"
    assert red.paths() == ["empresa.co/robots.txt", "empresa.co/", "www.empresa.co/robots.txt"]


def test_robots_con_error_5xx_bloquea():
    red = Red({"empresa.co/robots.txt": httpx.Response(503), "empresa.co/": _html("hola")})
    sitio, _ = _sitio(red)

    assert sitio.enriquecer(uuid4(), "empresa.co").estado == "fetch_bloqueado_por_robots"
    assert red.paths() == ["empresa.co/robots.txt"]


def test_conecta_a_la_ip_validada_con_el_host_original():
    """Anti-rebinding: se resuelve una vez y se conecta a esa IP; el transport nunca ve el nombre."""
    red = Red({"empresa.co/": _html("hola")})
    sitio, _ = _sitio(red)

    sitio.enriquecer(uuid4(), "empresa.co")

    assert red.requests
    assert {r.url.host for r in red.requests} == {PUBLICA}
    assert {r.headers["host"] for r in red.requests} == {"empresa.co"}


def test_user_agent_fijo_y_timeout_corto():
    red = Red({"empresa.co/": _html("hola")})
    sitio, _ = _sitio(red)

    sitio.enriquecer(uuid4(), "empresa.co")

    assert red.requests and SitioWeb.USER_AGENT
    for r in red.requests:
        assert r.headers["user-agent"] == SitioWeb.USER_AGENT
        assert "zenlo" not in r.headers["user-agent"].lower()  # confidencial: no se nombra en público
        assert "bot" in r.headers["user-agent"].lower()  # se identifica como crawler, no como python-httpx
        assert all(0 < t <= 10 for t in r.extensions["timeout"].values())


# --- Límites ----------------------------------------------------------------------------------------

def _cadena(saltos: int, final: httpx.Response) -> dict:
    rutas = {}
    for i in range(saltos):
        rutas[f"empresa.co/{'' if i == 0 else f'r{i}'}"] = httpx.Response(302, headers={"location": f"/r{i + 1}"})
    rutas[f"empresa.co/r{saltos}"] = final
    return rutas


def test_maximo_3_redirecciones():
    red = Red(_cadena(4, _html("fin")))
    sitio, _ = _sitio(red)

    with pytest.raises(DemasiadasRedirecciones):
        sitio.obtener(uuid4(), "https://empresa.co/")
    assert [p for p in red.paths() if not p.endswith("robots.txt")] == [
        "empresa.co/", "empresa.co/r1", "empresa.co/r2", "empresa.co/r3"]  # 4 requests, no 5

    red.requests.clear()
    assert sitio.enriquecer(uuid4(), "empresa.co").estado == "fallo"


def test_tres_redirecciones_se_siguen():
    red = Red(_cadena(3, _html('<a href="mailto:contacto@empresa.co">x</a>')))
    sitio, _ = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "ok"
    assert resultado.emails == ("contacto@empresa.co",)
    assert {r.url.host for r in red.requests} == {PUBLICA}  # anti-rebinding en cada salto
    assert {r.headers["host"] for r in red.requests} == {"empresa.co"}


def test_limite_de_tamano():
    leidos = 0

    def cuerpo():
        nonlocal leidos
        primero = b'<a href="mailto:contacto@empresa.co">x</a>'
        leidos += len(primero)
        yield primero
        while leidos < 3 * MB:
            leidos += CHUNK
            yield b"a" * CHUNK

    red = Red({"empresa.co/": lambda: httpx.Response(200, headers={"content-type": "text/html"}, content=cuerpo())})
    sitio, _ = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "truncado"
    assert resultado.emails == ("contacto@empresa.co",)  # lo leído se usa
    assert leidos <= 2 * MB + CHUNK


def test_gzip_bomb_se_corta_por_bytes_decodificados():
    bomba = gzip.compress(b'<a href="mailto:contacto@empresa.co">x</a>' + b"a" * (10 * MB))
    red = Red({"empresa.co/": httpx.Response(
        200, headers={"content-type": "text/html", "content-encoding": "gzip"}, content=bomba)})
    sitio, _ = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert len(bomba) < 2 * MB  # crudo chico: contar crudos no cortaría
    assert resultado.estado == "truncado"


def test_respeta_robots_txt():
    red = Red({
        "empresa.co/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /\n"),
        "empresa.co/": _html('<a href="mailto:contacto@empresa.co">x</a>'),
    })
    sitio, costos = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado == type(resultado)((), (), "fetch_bloqueado_por_robots")
    assert red.paths() == ["empresa.co/robots.txt"]  # sin GET de la raíz
    assert len(costos.filas) == 1  # robots.txt es request real (P9)


# --- Extracción -------------------------------------------------------------------------------------

def test_extrae_email_y_telefono_publicados():
    red = Red({"empresa.co/": _html(
        '<a href="mailto:contacto@empresa.co">Escribinos</a><footer>Tel: +57 601 234 5678</footer>')})
    sitio, _ = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "ok"
    assert resultado.emails == ("contacto@empresa.co",)
    assert resultado.telefonos == (("576012345678", "sitio_web"),)


def test_whatsapp_publicado_no_es_email_canal():
    red = Red({"empresa.co/": _html(
        '<a href="mailto:ventas@empresa.co">x</a>'
        '<a href="https://wa.me/573001234567">WhatsApp</a>'
        '<p>Llamanos al +57 300 765 4321</p>')})
    sitio, _ = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.emails == ("ventas@empresa.co",)  # el wa.me nunca puebla email
    assert resultado.telefonos[0] == ("573001234567", "whatsapp_comercial")  # gana al plano
    assert ("573007654321", "sitio_web") in resultado.telefonos


def test_sin_contacto_no_es_error():
    red = Red({"empresa.co/": _html("<p>Somos una empresa de logística.</p>")})
    sitio, _ = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert (resultado.emails, resultado.telefonos, resultado.estado) == ((), (), "ok")
    assert red.paths() == ["empresa.co/robots.txt", "empresa.co/"]


@pytest.mark.parametrize("estado", [404, 500])
def test_pagina_final_no_200_es_fallo_aunque_traiga_contacto(estado):
    red = Red({"empresa.co/": httpx.Response(estado, text='<a href="mailto:ventas@empresa.co">x</a>')})
    sitio, _ = _sitio(red)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert (resultado.emails, resultado.estado) == ((), "fallo")


# --- Costos y logs ----------------------------------------------------------------------------------

def test_un_web_fetch_por_request_real():
    red = Red({
        "empresa.co/": httpx.Response(302, headers={"location": "/r1"}),
        "empresa.co/r1": _html("hola"),
    })
    sitio, costos = _sitio(red)
    lead_id = uuid4()

    sitio.enriquecer(lead_id, "empresa.co")

    assert len(costos.filas) == len(red.requests) == 3  # robots + / + /r1
    for op in costos.filas:
        assert op.tipo == "web_fetch"
        assert op.lead_id == lead_id
        assert op.fuente is None and op.lote_id is None
        assert op.costo_unitario == TARIFA
        assert op.unidades == Decimal(1) and op.proveedor == "web" and op.moneda == "USD"
        assert op.canal is None and op.gratis is False
        assert type(op.unidades * op.costo_unitario) is Decimal


def test_dominio_no_ascii_viaja_en_punycode_y_una_fila_por_request():
    red = Red({"xn--caf-dma.co/": _html('<a href="mailto:hola@xn--caf-dma.co">x</a>')})
    sitio, costos = _sitio(red, {"xn--caf-dma.co": [PUBLICA]})

    resultado = sitio.enriquecer(uuid4(), "café.co")

    assert red.paths() == ["xn--caf-dma.co/robots.txt", "xn--caf-dma.co/"]
    assert len(costos.filas) == len(red.requests)
    assert (resultado.emails, resultado.estado) == (("hola@xn--caf-dma.co",), "ok")


def test_log_no_contiene_el_contacto_extraido(caplog):
    red = Red({"empresa.co/": _html(
        '<a href="mailto:contacto@empresa.co">x</a><a href="https://wa.me/573001234567">w</a>')})
    sitio, _ = _sitio(red)
    caplog.set_level(logging.DEBUG)

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.emails and resultado.telefonos
    assert "contacto@empresa.co" not in caplog.text
    assert "3001234567" not in caplog.text


# --- Revisión de seguridad final: ReDoS, token de robots, plazo total -------------------------------

def test_mailto_sin_arroba_no_es_cuadratico():
    import time
    red = Red({"empresa.co/": _html("mailto:" * 16_000)})  # 112 kB; la regex vieja tardaba ~7 s
    sitio, _ = _sitio(red)

    inicio = time.perf_counter()
    sitio.enriquecer(uuid4(), "empresa.co")

    assert time.perf_counter() - inicio < 0.5


def test_robots_que_bloquea_a_nuestro_bot_por_su_token_se_respeta():
    red = Red({
        "empresa.co/robots.txt": httpx.Response(200, text="User-agent: EnriquecedorBot\nDisallow: /\n"),
        "empresa.co/": _html('<a href="mailto:ventas@empresa.co">x</a>'),
    })
    sitio, _ = _sitio(red)

    assert sitio.enriquecer(uuid4(), "empresa.co").estado == "fetch_bloqueado_por_robots"
    assert red.paths() == ["empresa.co/robots.txt"]


def test_servidor_que_gotea_se_corta_por_plazo_total():
    reloj = [0.0]
    leidos = []

    def goteo():
        while True:
            reloj[0] += 4.0  # cada trozo llega justo antes del timeout de socket
            leidos.append(1)
            yield b"x" * 1024

    red = Red({"empresa.co/": lambda: httpx.Response(200, content=goteo())})
    sitio, _ = _sitio(red, reloj=lambda: reloj[0])

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert len(leidos) <= 10


def test_headers_lentos_cortan_la_cadena_de_saltos_por_plazo_total():
    reloj = [0.0]

    def lento(respuesta):
        def _():
            reloj[0] += 8.0  # cada respuesta tarda 8 s en llegar; ningún cuerpo se lee
            return respuesta
        return _

    red = Red({
        "empresa.co/robots.txt": lento(httpx.Response(404)),
        "empresa.co/": lento(httpx.Response(302, headers={"location": "/r1"})),
        "empresa.co/r1": lento(httpx.Response(302, headers={"location": "/r2"})),
        "empresa.co/r2": lento(_html("hola")),
    })
    sitio, costos = _sitio(red, reloj=lambda: reloj[0])

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert red.paths() == ["empresa.co/robots.txt", "empresa.co/", "empresa.co/r1"]  # t=24 > 20 antes de /r2
    assert len(costos.filas) == 3


def test_robots_lento_corta_antes_de_pedir_la_pagina_del_mismo_salto():
    reloj = [0.0]

    def robots_lento():
        reloj[0] += 25.0  # robots se come el plazo entero; la página del mismo salto no se pide
        return httpx.Response(404)

    red = Red({"empresa.co/robots.txt": robots_lento, "empresa.co/": _html("hola")})
    sitio, costos = _sitio(red, reloj=lambda: reloj[0])

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert red.paths() == ["empresa.co/robots.txt"]
    assert len(costos.filas) == 1


def test_httpx_no_loguea_ip_ni_ruta_de_cada_salto(caplog):
    caplog.set_level(logging.INFO)
    sitio, _ = _sitio(Red({"empresa.co/": _html("hola")}))

    sitio.enriquecer(uuid4(), "empresa.co")

    assert [r for r in caplog.records if r.name.startswith(("httpx", "httpcore"))] == []


def test_dns_lento_vence_el_plazo_sin_request_ni_costo():
    reloj = [0.0]

    def dns_lento(host):
        reloj[0] += 25.0
        return [PUBLICA]

    red = Red({"empresa.co/": _html("hola")})
    costos = RegistroCostosFalso()
    sitio = SitioWeb(costos, httpx.MockTransport(red), dns_lento, TARIFA, reloj=lambda: reloj[0])

    resultado = sitio.enriquecer(uuid4(), "empresa.co")

    assert resultado.estado == "fallo"
    assert red.paths() == []
    assert costos.filas == []
