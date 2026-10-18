"""croma_supersociedades_co (T017). Por ahora, los LÍMITES (parte del tope, revisión del advisor): sin red, con
httpx.MockTransport y un libro falso. El resto de T017 (mapeo, créditos, reintentos, parseo) llega después."""
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.modulos.descubrimiento.dominio.errores import LimiteFuenteAgotado
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente
from app.modulos.descubrimiento.infraestructura.adaptadores.croma_supersociedades import CromaSupersociedadesCo
from tests.falsos import RegistroCostosFalso

TARIFA = Decimal("0.00099")
LIMITES = {"croma_requests_por_24h": 100, "croma_creditos_gratis_mes": 1500}
META = MetaFuente(clave="croma_supersociedades_co", proveedor="croma", paises=frozenset({"CO"}),
                  filtros=frozenset({"ciiu", "departamento", "ingresos_min"}), trae=frozenset({"nit", "nombre"}),
                  tipo="dataset", licencia="datos públicos vía Croma; no redistribuir", endpoint="/co/supersociedades/companies-search/v1",
                  tipo_titular_implicito="juridica")
CRITERIOS = CriteriosICP("CO", {"ciiu": "4711", "departamento": "11"})
LOTE = uuid4()
CUERPO_VACIO = {"data": [], "total": 0}  # sintético: la forma real se contrasta en la corrida T048


def _adaptador(requests_24h=0, creditos_mes=Decimal(0), limites=LIMITES, tarifa=TARIFA):
    pedidas = []

    def responder(request):
        pedidas.append(request)
        return httpx.Response(200, json=CUERPO_VACIO)

    costos = RegistroCostosFalso(requests_24h=requests_24h, creditos_mes=creditos_mes)
    adaptador = CromaSupersociedadesCo(
        meta=META, registro_costos=costos, transporte=httpx.MockTransport(responder), costo_unitario=tarifa,
        lote_id=LOTE, api_key="clave-de-prueba", limites=limites)
    return adaptador, pedidas, costos


def test_no_llama_si_se_agoto_el_limite_de_24h():
    adaptador, pedidas, costos = _adaptador(requests_24h=100)

    with pytest.raises(LimiteFuenteAgotado):
        adaptador.buscar(CRITERIOS, 1)

    assert pedidas == [] and costos.filas == []  # sin request no hay fila: no se gastó nada


def test_limite_de_24h_usa_requests_no_creditos():
    adaptador, pedidas, costos = _adaptador(requests_24h=99, creditos_mes=Decimal(990))

    adaptador.buscar(CRITERIOS, 1)  # 99 requests: la 100 todavía entra

    assert len(pedidas) == 1


def test_no_llama_si_el_cupo_mensual_no_alcanza_para_otro_credito():
    adaptador, pedidas, costos = _adaptador(creditos_mes=Decimal(1500))  # 1500 + 1 > 1500

    with pytest.raises(LimiteFuenteAgotado):
        adaptador.buscar(CRITERIOS, 1)

    assert pedidas == [] and costos.filas == []


def test_el_ultimo_credito_del_cupo_mensual_si_se_llama_y_sale_gratis():
    adaptador, pedidas, costos = _adaptador(creditos_mes=Decimal(1499))  # 1499 + 1 = 1500 <= 1500

    adaptador.buscar(CRITERIOS, 1)

    assert len(pedidas) == 1
    assert [(f.tipo, f.unidades, f.costo_unitario, f.gratis) for f in costos.filas] == [
        ("croma_consulta", Decimal(1), TARIFA, True)]  # gratis, pero a valor de lista (para el CPL y el tope)
    # Con lote_id=None `gasto_busqueda` daría 0 y el tope nunca cortaría; el límite se cuenta por proveedor "croma".
    (fila,) = costos.filas
    assert (fila.lote_id, fila.proveedor, fila.fuente, fila.lead_id) == (LOTE, "croma", "croma_supersociedades_co", None)
    assert costos.gasto_busqueda(LOTE) == TARIFA


def test_costo_maximo_llamada_es_un_credito_a_la_tarifa_que_recibe():
    adaptador, _, _ = _adaptador(tarifa=Decimal("0.005"))  # no la constante 0.00099

    assert adaptador.meta.costo_maximo_llamada == Decimal("0.005")
    assert type(adaptador.meta.costo_maximo_llamada) is Decimal


def test_los_limites_salen_de_fuentes_yaml_no_de_constantes():
    chicos = {"croma_requests_por_24h": 5, "croma_creditos_gratis_mes": 10}

    por_requests, pedidas, _ = _adaptador(requests_24h=5, limites=chicos)
    with pytest.raises(LimiteFuenteAgotado):
        por_requests.buscar(CRITERIOS, 1)

    por_creditos, pedidas2, _ = _adaptador(creditos_mes=Decimal(10), limites=chicos)
    with pytest.raises(LimiteFuenteAgotado):
        por_creditos.buscar(CRITERIOS, 1)

    assert pedidas == [] and pedidas2 == []


# --- mapeo, créditos, reintentos (fixture SINTÉTICA con la forma documentada: `data` y `total`) --------------------

import json  # noqa: E402

from app.modulos.descubrimiento.dominio.errores import CriterioNoSoportado, FuenteNoDisponible  # noqa: E402

EMPRESAS = {"total": 2015, "data": [
    {"nit": "900.123.456-7", "name": "SUPERMERCADOS EJEMPLO S.A.S.", "city": "BOGOTÁ", "address": "CL 1 # 2-3", "ciiu_code": "4711"},
    {"nit": "", "name": "SIN NIT S.A."},  # no se puede dedupar: se descarta
]}


def _con_respuestas(*respuestas, requests_24h=0, creditos_mes=Decimal(0), esperas=None):
    """Un adaptador que contesta las `respuestas` en orden (httpx.Response o una excepción a lanzar)."""
    pedidas, cola = [], list(respuestas)

    def responder(request):
        pedidas.append(request)
        r = cola.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    costos = RegistroCostosFalso(requests_24h=requests_24h, creditos_mes=creditos_mes)
    a = CromaSupersociedadesCo(
        meta=META, registro_costos=costos, transporte=httpx.MockTransport(responder), costo_unitario=TARIFA,
        lote_id=LOTE, api_key="clave-secreta-de-prueba", limites=LIMITES,
        dormir=(esperas.append if esperas is not None else lambda s: None))
    return a, pedidas, costos


def test_mapea_la_respuesta_a_empresas_juridicas_con_total():
    a, pedidas, _ = _con_respuestas(httpx.Response(200, json=EMPRESAS))

    pagina = a.buscar(CRITERIOS, 1)

    assert pagina.total == 2015 and len(pagina.empresas) == 1  # `total` de Croma, no len(data)
    e = pagina.empresas[0]
    assert (e.id_fiscal, e.tipo_titular, e.actividad, e.pais, e.fuente) == (
        "900123456", "juridica", ("4711", "CIIU"), "CO", "croma_supersociedades_co")
    assert (e.ciudad, e.direccion) == ("BOGOTÁ", "CL 1 # 2-3")
    assert "clave-secreta" not in e.url_origen and "?" in e.url_origen and e.url_origen.endswith("?nit=900123456")


def test_body_enviado_a_croma_y_la_key_solo_en_el_header():
    a, pedidas, _ = _con_respuestas(httpx.Response(200, json=EMPRESAS))

    a.buscar(CriteriosICP("CO", {"ciiu": "4711", "departamento": "11", "ingresos_min": "5000000"}), 1)

    (r,) = pedidas
    assert json.loads(r.content) == {"page": 1, "per_page": 100, "ciiu_code": "4711", "department": "11", "min_revenue": 5000000}
    assert "clave-secreta" not in r.content.decode() and "clave-secreta" not in str(r.url)
    assert r.headers["authorization"] == "Bearer clave-secreta-de-prueba"
    assert "clave-secreta" not in repr(a)


def test_criterio_no_soportado_no_hace_request():
    a, pedidas, costos = _con_respuestas()

    with pytest.raises(CriterioNoSoportado):
        a.buscar(CriteriosICP("CO", {"ciiu": "4711", "__criterio_inexistente__": "x"}), 1)

    assert pedidas == [] and costos.filas == []


def test_un_502_seguido_de_un_200_registra_cada_intento():
    esperas = []
    a, pedidas, costos = _con_respuestas(httpx.Response(502), httpx.Response(200, json=EMPRESAS), esperas=esperas)

    pagina = a.buscar(CRITERIOS, 1)

    assert len(pedidas) == 2 and len(pagina.empresas) == 1 and esperas == [1.0]
    assert [(f.unidades, f.costo_unitario) for f in costos.filas] == [(Decimal(0), Decimal(0)), (Decimal(1), TARIFA)]
    assert costos.gasto_busqueda(LOTE) == TARIFA  # el intento fallido no infla el gasto


def test_502_con_99_previas_no_reintenta_y_la_fila_queda_escrita():
    a, pedidas, costos = _con_respuestas(httpx.Response(502), requests_24h=99)
    costos_registrar = costos.registrar
    costos.registrar = lambda op: (costos_registrar(op), setattr(costos, "_requests_24h", {"croma": 100}))

    with pytest.raises(LimiteFuenteAgotado):
        a.buscar(CRITERIOS, 1)

    assert len(pedidas) == 1 and len(costos.filas) == 1 and costos.filas[0].unidades == 0


def test_429_lanza_limite_sin_reintento_y_con_fila_en_cero():
    a, pedidas, costos = _con_respuestas(httpx.Response(429), httpx.Response(200, json=EMPRESAS))

    with pytest.raises(LimiteFuenteAgotado):
        a.buscar(CRITERIOS, 1)

    assert len(pedidas) == 1 and [f.unidades for f in costos.filas] == [0]


def test_timeout_dos_veces_es_fuente_no_disponible_con_dos_filas_en_cero():
    a, pedidas, costos = _con_respuestas(httpx.ReadTimeout("t"), httpx.ReadTimeout("t"))

    with pytest.raises(FuenteNoDisponible):
        a.buscar(CRITERIOS, 1)

    assert len(pedidas) == 2 and [f.unidades for f in costos.filas] == [0, 0]


@pytest.mark.parametrize("cuerpo", [b'{"data": [', b'{"foo": 1}', b'{"data": [], "total": "2015"}'], ids=["truncado", "sin_data_ni_total", "total_str"])
def test_200_que_no_parsea_cobra_el_credito_y_no_filtra_el_cuerpo(cuerpo):
    a, _, costos = _con_respuestas(httpx.Response(200, content=cuerpo))

    with pytest.raises(FuenteNoDisponible) as error:
        a.buscar(CRITERIOS, 1)

    assert [(f.unidades, f.costo_unitario) for f in costos.filas] == [(Decimal(1), TARIFA)]  # Croma cobró el 200
    assert "foo" not in str(error.value) and "clave-secreta" not in str(error.value)
