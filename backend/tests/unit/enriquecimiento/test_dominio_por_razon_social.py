"""DominioPorRazonSocial: DNS primero, SSRF por salto, verificación obligatoria, costos por request. Sin red."""
from decimal import Decimal
from uuid import uuid4

import httpx

from app.modulos.enriquecimiento.infraestructura.adaptadores.dominio_por_razon_social import DominioPorRazonSocial
from app.modulos.enriquecimiento.infraestructura.adaptadores.sitio_web import SitioWeb
from tests.falsos import RegistroCostosFalso

PUBLICA = "93.184.216.34"
TARIFA = Decimal("0.00001")
NIT = "900123456"
RAZON = "GRUPO PROCESSA S.A.S"


class Red:
    """Rutea por Host + path y anota cada request que llega al transporte."""

    def __init__(self, rutas: dict):
        self.rutas = rutas
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        r = self.rutas.get(request.headers["host"], httpx.Response(404))
        return r(request) if callable(r) else r

    def hosts(self) -> list[str]:
        return [r.headers["host"] for r in self.requests]


class Dns:
    def __init__(self, tabla: dict[str, list[str]]):
        self.tabla = tabla
        self.consultas: list[str] = []

    def __call__(self, host: str) -> list[str]:
        self.consultas.append(host)
        if host not in self.tabla:
            raise OSError("Name or service not known")
        return self.tabla[host]


def _pagina(cuerpo: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<html><body>{cuerpo}</body></html>")


def _buscador(rutas: dict, dns: dict, **kw):
    red, costos = Red(rutas), RegistroCostosFalso()
    resolver = Dns(dns)
    return DominioPorRazonSocial(costos, httpx.MockTransport(red), resolver, TARIFA, **kw), red, costos, resolver


def test_acepta_el_dominio_cuya_pagina_trae_el_nit():
    b, red, _, _ = _buscador({"grupoprocessa.com.co": _pagina("Grupo Procesos NIT 900.123.456-7")},
                             {"grupoprocessa.com.co": [PUBLICA]})

    e = b.buscar(uuid4(), RAZON, NIT)

    assert (e.dominio, e.url, e.motivo) == ("grupoprocessa.com.co", "https://grupoprocessa.com.co/", "nit")


def test_acepta_por_razon_social_si_no_hay_nit():
    b, _, _, _ = _buscador({"grupoprocessa.com": _pagina("Bienvenidos a Grupo Processa")}, {"grupoprocessa.com": [PUBLICA]})

    e = b.buscar(uuid4(), RAZON, None)

    assert (e.dominio, e.motivo) == ("grupoprocessa.com", "razon_social")


def test_pagina_que_no_menciona_la_empresa_no_se_acepta():
    b, red, _, _ = _buscador({h: _pagina("Dominio en venta. Escribanos a ventas@parking.example")
                              for h in ("grupoprocessa.com.co", "grupoprocessa.com", "grupoprocessa.co")},
                             {h: [PUBLICA] for h in ("grupoprocessa.com.co", "grupoprocessa.com", "grupoprocessa.co")})

    assert b.buscar(uuid4(), RAZON, NIT) is None
    assert len(red.requests) == 3  # los pidió y los descartó; nunca acepta sin verificar


def test_el_primer_candidato_verificado_gana_y_no_se_piden_mas():
    ok = _pagina("Grupo Processa")
    b, red, _, _ = _buscador({"grupoprocessa.com.co": _pagina("otra empresa"), "grupoprocessa.com": ok, "grupoprocessa.co": ok},
                             {h: [PUBLICA] for h in ("grupoprocessa.com.co", "grupoprocessa.com", "grupoprocessa.co")})

    assert b.buscar(uuid4(), RAZON, None).dominio == "grupoprocessa.com"
    assert red.hosts() == ["grupoprocessa.com.co", "grupoprocessa.com"]


def test_dns_que_no_resuelve_se_descarta_sin_http():
    b, red, costos, resolver = _buscador({}, {})

    assert b.buscar(uuid4(), RAZON, NIT) is None
    assert red.requests == [] and costos.filas == []
    assert len(resolver.consultas) == 6  # probó los seis y ninguno llegó a HTTP


def test_dns_que_resuelve_vacio_tampoco_hace_http():
    b, red, _, _ = _buscador({}, {"grupoprocessa.com.co": []})

    assert b.buscar(uuid4(), RAZON, NIT) is None
    assert red.requests == []


def test_un_dominio_que_resuelve_a_ip_privada_no_se_pide():
    privada = _pagina("Grupo Processa NIT 900123456")
    b, red, costos, _ = _buscador({"grupoprocessa.com.co": privada}, {"grupoprocessa.com.co": ["10.0.0.5"]})

    assert b.buscar(uuid4(), RAZON, NIT) is None
    assert red.requests == [] and costos.filas == []


def test_una_redireccion_a_ip_privada_se_corta():
    rutas = {"grupoprocessa.com.co": httpx.Response(302, headers={"location": "https://www.grupoprocessa.com.co/"}),
             "www.grupoprocessa.com.co": _pagina("Grupo Processa")}
    b, red, _, _ = _buscador(rutas, {"grupoprocessa.com.co": [PUBLICA], "www.grupoprocessa.com.co": ["169.254.169.254"]})

    assert b.buscar(uuid4(), RAZON, None) is None
    assert red.hosts() == ["grupoprocessa.com.co"]


def test_una_redireccion_a_otro_dominio_no_se_sigue():
    rutas = {"grupoprocessa.com.co": httpx.Response(302, headers={"location": "https://otra.example/"}),
             "otra.example": _pagina("Grupo Processa")}
    b, red, _, _ = _buscador(rutas, {"grupoprocessa.com.co": [PUBLICA], "otra.example": [PUBLICA]})

    assert b.buscar(uuid4(), RAZON, None) is None
    assert "otra.example" not in red.hosts()


def test_una_redireccion_a_www_del_mismo_dominio_se_sigue():
    rutas = {"grupoprocessa.com.co": httpx.Response(301, headers={"location": "https://www.grupoprocessa.com.co/"}),
             "www.grupoprocessa.com.co": _pagina("Grupo Processa")}
    b, _, costos, _ = _buscador(rutas, {"grupoprocessa.com.co": [PUBLICA], "www.grupoprocessa.com.co": [PUBLICA]})

    assert b.buscar(uuid4(), RAZON, None).dominio == "grupoprocessa.com.co"
    assert len(costos.filas) == 2  # cada request, redirección incluida


def test_cada_request_escribe_web_fetch_con_lead_id_antes_de_devolver():
    lead = uuid4()
    b, red, costos, _ = _buscador({"grupoprocessa.com": _pagina("Grupo Processa")},
                                  {"grupoprocessa.com.co": [PUBLICA], "grupoprocessa.com": [PUBLICA]})

    b.buscar(lead, RAZON, None)

    assert len(costos.filas) == len(red.requests) == 2
    for op in costos.filas:
        assert (op.tipo, op.proveedor, op.lead_id, op.lote_id, op.unidades, op.costo_unitario, op.moneda) == (
            "web_fetch", "web", lead, None, Decimal(1), TARIFA, "USD")


def test_el_costo_se_escribe_aunque_el_pedido_falle():
    def cae(request):
        raise httpx.ConnectError("boom")
    b, red, costos, _ = _buscador({"grupoprocessa.com.co": cae}, {"grupoprocessa.com.co": [PUBLICA]})

    assert b.buscar(uuid4(), RAZON, None) is None
    assert len(costos.filas) == 1


def test_mismo_user_agent_que_sitio_web_y_conexion_a_la_ip_validada():
    b, red, _, _ = _buscador({"grupoprocessa.com.co": _pagina("Grupo Processa")}, {"grupoprocessa.com.co": [PUBLICA]})

    b.buscar(uuid4(), RAZON, None)

    (r,) = red.requests
    assert r.headers["user-agent"] == SitioWeb.USER_AGENT and r.url.host == PUBLICA and r.extensions["sni_hostname"] == "grupoprocessa.com.co"


def test_timeout_de_4_segundos_por_request():
    visto = {}

    def mira(request):
        visto.update(request.extensions["timeout"])
        return _pagina("Grupo Processa")
    b, _, _, _ = _buscador({"grupoprocessa.com.co": mira}, {"grupoprocessa.com.co": [PUBLICA]})

    b.buscar(uuid4(), RAZON, None)

    assert visto == {"connect": 4.0, "read": 4.0, "write": 4.0, "pool": 4.0}


def test_razon_social_sin_candidatos_no_hace_dns_ni_http():
    b, red, costos, resolver = _buscador({}, {})

    assert b.buscar(uuid4(), "COMERCIAL SAS", NIT) is None
    assert resolver.consultas == [] and red.requests == [] and costos.filas == []


def test_plazo_total_por_lead_corta_los_candidatos_que_faltan():
    tiempo = [0.0]
    hojas = {h: _pagina("nada") for h in ("grupoprocessa.com.co", "grupoprocessa.com", "grupoprocessa.co")}

    def reloj():
        tiempo[0] += 5.0  # cada vez que el adaptador mira la hora pasan 5 s
        return tiempo[0]
    b, red, _, _ = _buscador(hojas, {h: [PUBLICA] for h in hojas}, reloj=reloj, plazo_s=12.0)

    assert b.buscar(uuid4(), RAZON, NIT) is None
    assert 0 < len(red.requests) < 6


def test_respuesta_no_200_se_descarta():
    b, _, _, _ = _buscador({"grupoprocessa.com.co": httpx.Response(500, text="Grupo Processa")},
                           {"grupoprocessa.com.co": [PUBLICA]})

    assert b.buscar(uuid4(), RAZON, None) is None
