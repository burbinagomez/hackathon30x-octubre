"""Contrato de ClasificadorEncaje: JevFalso y JevClasificador (transporte falso) se comportan igual, costo incluido. Sin red."""
from decimal import Decimal
from typing import get_args
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.modulos.enriquecimiento.dominio.errores import JevNoDisponible, SalidaJevInvalida, UsoJevInvalido
from app.modulos.enriquecimiento.dominio.puertos import Encaje
from app.modulos.enriquecimiento.infraestructura.adaptadores.jev_clasificador import JevClasificador, cuerpo_jev
from tests.falsos import JevFalso, RegistroCostosFalso

ETIQUETAS = get_args(Encaje.__annotations__["etiqueta"])
ROTA = {"etiqueta": "tal_vez", "probabilidad": 1.3, "razon": "x"}


def _falso(salida: dict, costos: RegistroCostosFalso, tokens_in=500) -> JevFalso:
    return JevFalso(salida, costos, tokens_in)


def _jev(salida: dict, costos: RegistroCostosFalso, tokens_in=500) -> JevClasificador:
    transporte = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"salida": salida, "uso": {"tokens_in": tokens_in}}))
    return JevClasificador(costos, transporte, "https://jev.invalid/v1/clasificar", SecretStr("credencial-sintetica"),
                           Decimal("0.042"))


CLASIFICADORES = pytest.mark.parametrize("fabrica", [_falso, _jev], ids=["falso", "jev"])


ARGS = ("agentes de carga", "Transportes Andinos SAS", "Cali", None)
TECHO = len(cuerpo_jev(*ARGS))  # bytes del body que JevClasificador manda


def _clasificar(clasificador) -> Encaje:
    return clasificador.clasificar(uuid4(), *ARGS)


def _filas(costos: RegistroCostosFalso) -> list[tuple]:
    return [(op.tipo, op.proveedor, op.unidades, op.unidades * op.costo_unitario) for op in costos.filas]


@CLASIFICADORES
def test_devuelve_etiqueta_del_enum(fabrica):
    encaje = _clasificar(fabrica({"etiqueta": "no_encaja", "probabilidad": 0.2, "razon": "x"}, RegistroCostosFalso()))

    assert isinstance(encaje, Encaje)
    assert encaje.etiqueta in ETIQUETAS
    assert (encaje.etiqueta, encaje.probabilidad) == ("no_encaja", 0.2)  # la salida configurada, no una constante


@CLASIFICADORES
def test_salida_rota_lanza_y_deja_el_costo(fabrica):
    costos = RegistroCostosFalso()

    with pytest.raises(SalidaJevInvalida):
        _clasificar(fabrica(ROTA, costos))

    assert _filas(costos) == [("jev_tokens", "jev", Decimal(500), Decimal("0.000021"))]


@CLASIFICADORES
def test_registra_costo(fabrica):
    costos = RegistroCostosFalso()

    _clasificar(fabrica({"etiqueta": "encaja", "probabilidad": 0.9, "razon": "x"}, costos))

    assert _filas(costos) == [("jev_tokens", "jev", Decimal(500), Decimal("0.000021"))]


@CLASIFICADORES
def test_uso_invalido_cobra_el_techo_y_lanza(fabrica):
    costos = RegistroCostosFalso()

    with pytest.raises(UsoJevInvalido):
        _clasificar(fabrica({"etiqueta": "encaja", "probabilidad": 0.9, "razon": "x"}, costos, tokens_in=-1))

    assert _filas(costos) == [("jev_tokens", "jev", Decimal(TECHO), Decimal("0.042") * TECHO / 1_000_000)]


def _jev_que_responde(responder, costos: RegistroCostosFalso) -> JevClasificador:
    return JevClasificador(costos, httpx.MockTransport(responder), "https://jev.invalid/v1/clasificar",
                           SecretStr("credencial-sintetica"), Decimal("0.042"))


def _timeout(request):
    raise httpx.ReadTimeout("sintetico", request=request)


@pytest.mark.parametrize("responder, unidades", [
    (lambda r: httpx.Response(503, text="caido"), 0),   # jev no procesó: fila en 0
    (lambda r: httpx.Response(504, text="tarde"), TECHO),  # el gateway cortó, jev pudo haber procesado: techo
    (_timeout, TECHO),                                  # timeout propio: no sabemos, techo
], ids=["503", "504", "timeout"])
def test_falla_http_registra_costo_y_lanza_jev_no_disponible(responder, unidades):
    costos = RegistroCostosFalso()

    with pytest.raises(JevNoDisponible):
        _clasificar(_jev_que_responde(responder, costos))

    assert _filas(costos) == [("jev_tokens", "jev", Decimal(unidades), Decimal("0.042") * unidades / 1_000_000)]
