import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.descubrimiento.aplicacion.registro import cargar_registro
from app.modulos.descubrimiento.dominio.errores import CriterioNoSoportado, FuenteNoDisponible
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


def test_mapea_elemento_a_empresa_cruda(adaptador):
    pagina = adaptador.buscar(ICP_BOGOTA, 1)

    por_url = {e.url_origen: e for e in pagina.empresas}
    assert set(por_url) == {
        "https://www.openstreetmap.org/node/123",
        "https://www.openstreetmap.org/way/456",
    }
    nodo = por_url["https://www.openstreetmap.org/node/123"]
    assert nodo.nombre == "Supermercado Ficticio La Prueba"
    assert nodo.pais == "CO"
    assert nodo.fuente == "osm_overpass"
    assert nodo.ciudad == "Bogotá D.C."  # addr:city
    assert nodo.direccion == "Calle Inventada 12-34"
    assert nodo.as_of == datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    assert nodo.actividad == ("shop=supermarket", "OSM")
    assert nodo.tipo_titular == "desconocido"
    assert nodo.id_fiscal is None
    assert nodo.web is None
    assert adaptador.meta.licencia == "ODbL"

    way = por_url["https://www.openstreetmap.org/way/456"]
    assert way.ciudad == "Bogotá"  # sin addr:city, la ciudad buscada
    assert way.direccion is None
    assert way.actividad == ("shop=convenience", "OSM")
    assert pagina.total is None


def test_elemento_sin_nombre_se_descarta(adaptador):
    pagina = adaptador.buscar(ICP_BOGOTA, 1)

    assert len(pagina.empresas) == 2
    assert all(e.nombre for e in pagina.empresas)
    assert "https://www.openstreetmap.org/node/789" not in {e.url_origen for e in pagina.empresas}


class RelojFalso:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora


# Distinta de computo_seg_usd (0.0000070): la fila tiene que traer la tarifa del constructor, no una fija.
TARIFA = Decimal("0.0000099")


def _fila(segundos: int, lote_id) -> OperacionCosto:
    return OperacionCosto(
        tipo="overpass_query",
        unidades=Decimal(segundos),
        costo_unitario=TARIFA,
        moneda="USD",
        proveedor="osm",
        fuente="osm_overpass",
        canal=None,
        lead_id=None,
        lote_id=lote_id,
        gratis=False,
    )


def _adaptador_con_reloj(meta, respuesta: httpx.Response, segundos: float):
    """El transporte avanza el reloj `segundos` durante el request, como un request real."""
    reloj, costos, lote_id = RelojFalso(), RegistroCostosFalso(), uuid4()

    def responder(request: httpx.Request) -> httpx.Response:
        reloj.ahora += segundos
        return respuesta

    adaptador = OsmOverpass(
        meta=meta,
        registro_costos=costos,
        transporte=httpx.MockTransport(responder),
        costo_unitario=TARIFA,
        lote_id=lote_id,
        repo_url=REPO_URL,
        reloj=reloj,
    )
    return adaptador, costos, lote_id


def test_registra_segundos_de_cada_intento(meta):
    ok = httpx.Response(200, json=json.loads(FIXTURE.read_text()))
    adaptador, costos, lote_id = _adaptador_con_reloj(meta, ok, segundos=2)

    adaptador.buscar(ICP_BOGOTA, 1)

    assert costos.filas == [_fila(2, lote_id)]
    assert isinstance(costos.filas[0].unidades, Decimal)


def test_fallo_se_reporta_sin_tragarlo(meta):
    cuerpo = "CUERPO-INTERNO-DEL-SERVIDOR"
    adaptador, costos, lote_id = _adaptador_con_reloj(meta, httpx.Response(500, text=cuerpo), segundos=3)

    # finally: la fila se exige aunque buscar() lance otra cosa; así el rojo es este assert.
    try:
        with pytest.raises(FuenteNoDisponible) as error:
            adaptador.buscar(ICP_BOGOTA, 1)
    finally:
        assert costos.filas == [_fila(3, lote_id)]

    assert cuerpo not in str(error.value)
    assert cuerpo not in repr(error.value)
    assert cuerpo not in repr(error.value.__cause__)


def test_rechaza_criterio_no_soportado_sin_request(adaptador, enviados):
    icp = CriteriosICP("CO", {"ciudad": "Bogotá", "departamento": "11"})

    with pytest.raises(CriterioNoSoportado):
        adaptador.buscar(icp, 1)
    assert enviados == []
