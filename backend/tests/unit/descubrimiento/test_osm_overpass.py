import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.descubrimiento.aplicacion.registro import cargar_registro
from app.modulos.descubrimiento.dominio.errores import CriterioNoSoportado
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.infraestructura.adaptadores.osm_overpass import OsmOverpass

BACKEND = Path(__file__).resolve().parents[3]
FIXTURE = BACKEND / "tests" / "fixtures" / "osm" / "bogota_4711.json"
REPO_URL = "https://example.invalid/repo-del-reto"
ICP_BOGOTA = CriteriosICP("CO", {"ciudad": "Bogotá", "tipo_negocio": ("shop=supermarket", "shop=convenience")})


class RegistroCostosFalso:
    def __init__(self):
        self.filas: list[OperacionCosto] = []

    def registrar(self, op: OperacionCosto) -> None:
        self.filas.append(op)

    def requests_24h(self, proveedor: str) -> int:
        return 0

    def creditos_mes(self, proveedor: str) -> int:
        return 0


@pytest.fixture
def meta():
    registro = cargar_registro(BACKEND / "config" / "fuentes.yaml", {"osm_overpass": object})
    return registro.fuentes["osm_overpass"][1]


@pytest.fixture
def enviados() -> list[httpx.Request]:
    return []


@pytest.fixture
def transporte(enviados):
    def responder(request: httpx.Request) -> httpx.Response:
        enviados.append(request)
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    return httpx.MockTransport(responder)


@pytest.fixture
def adaptador(meta, transporte):
    return OsmOverpass(
        meta=meta,
        registro_costos=RegistroCostosFalso(),
        transporte=transporte,
        costo_unitario=Decimal("0.0000070"),
        lote_id=uuid4(),
        repo_url=REPO_URL,
    )


def _query(request: httpx.Request) -> str:
    return parse_qs(request.content.decode())["data"][0]


def test_query_acotada_con_timeout_y_tope(adaptador, enviados):
    adaptador.buscar(ICP_BOGOTA, 1)

    assert len(enviados) == 1
    assert enviados[0].method == "POST"
    query = _query(enviados[0])
    for trozo in (
        "[out:json][timeout:25]",
        '"ISO3166-1"="CO"',
        '"name"="Bogotá"',
        '["shop"="supermarket"]["name"]',
        '["shop"="convenience"]["name"]',
        "out center tags 500",
    ):
        assert trozo in query


def test_envia_user_agent_identificable(adaptador, enviados):
    adaptador.buscar(ICP_BOGOTA, 1)

    agente = enviados[0].headers["User-Agent"]
    assert agente.startswith("dapta-reto-30x/")
    assert REPO_URL in agente


def test_rechaza_criterio_no_soportado_sin_request(adaptador, enviados):
    icp = CriteriosICP("CO", {"ciudad": "Bogotá", "departamento": "11"})

    with pytest.raises(CriterioNoSoportado):
        adaptador.buscar(icp, 1)
    assert enviados == []
