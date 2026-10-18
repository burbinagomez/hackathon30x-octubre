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
CUERPO_VACIO = {"data": [], "total": 0}  # sintético: la forma real se contrasta en la corrida T048


def _adaptador(requests_24h=0, creditos_mes=Decimal(0), limites=LIMITES):
    pedidas = []

    def responder(request):
        pedidas.append(request)
        return httpx.Response(200, json=CUERPO_VACIO)

    costos = RegistroCostosFalso(requests_24h=requests_24h, creditos_mes=creditos_mes)
    adaptador = CromaSupersociedadesCo(
        meta=META, registro_costos=costos, transporte=httpx.MockTransport(responder), costo_unitario=TARIFA,
        lote_id=uuid4(), api_key="clave-de-prueba", limites=limites)
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


def test_los_limites_salen_de_fuentes_yaml_no_de_constantes():
    chicos = {"croma_requests_por_24h": 5, "croma_creditos_gratis_mes": 10}

    por_requests, pedidas, _ = _adaptador(requests_24h=5, limites=chicos)
    with pytest.raises(LimiteFuenteAgotado):
        por_requests.buscar(CRITERIOS, 1)

    por_creditos, pedidas2, _ = _adaptador(creditos_mes=Decimal(10), limites=chicos)
    with pytest.raises(LimiteFuenteAgotado):
        por_creditos.buscar(CRITERIOS, 1)

    assert pedidas == [] and pedidas2 == []
