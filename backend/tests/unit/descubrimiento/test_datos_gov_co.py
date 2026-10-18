import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.descubrimiento.aplicacion.camaras import cargar_camaras
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente
from app.modulos.descubrimiento.infraestructura.adaptadores.datos_gov_co_rues import (
    DatosGovCoRues,
)

BACKEND = Path(__file__).resolve().parents[3]
FIXTURES = BACKEND / "tests" / "fixtures" / "datos_gov_co"
CAMARAS = cargar_camaras(BACKEND / "config" / "camaras_co.yaml")
CRITERIOS = CriteriosICP(pais="CO", filtros={"ciiu": "4711", "departamento": "11"})

SELECT_FILAS = "nit,digito_verificacion,razon_social,cod_ciiu_act_econ_pri,codigo_camara,organizacion_juridica,fecha_renovacion"
# Literal de spec.md (Decisiones técnicas): las 6 cláusulas unidas por AND.
WHERE_FILAS = (
    "organizacion_juridica != 'PERSONA NATURAL'"
    " AND organizacion_juridica IS NOT NULL"
    " AND estado_matricula = 'ACTIVA'"
    " AND cod_ciiu_act_econ_pri = '4711'"
    " AND codigo_camara in('04')"
    " AND nit IS NOT NULL"
)
COLUMNAS_DE_PERSONAS = (
    "numero_identificacion",
    "primer_nombre",
    "segundo_nombre",
    "primer_apellido",
    "segundo_apellido",
    "representante_legal",
    "num_identificacion_representante_legal",
    "clase_identificacion_rl",
)


class CostosEnMemoria:
    def __init__(self) -> None:
        self.filas: list[OperacionCosto] = []

    def registrar(self, op: OperacionCosto) -> None:
        self.filas.append(op)

    def requests_24h(self, proveedor: str) -> int:
        return 0

    def creditos_mes(self, proveedor: str):
        return 0


def _cargar(nombre: str) -> list[dict]:
    return json.loads((FIXTURES / nombre).read_text())


def _adaptador(fixture_filas: str) -> tuple[DatosGovCoRues, list[httpx.Request]]:
    capturadas: list[httpx.Request] = []
    filas = _cargar(fixture_filas)
    conteo = _cargar("conteo_naturales.json")

    def responder(request: httpx.Request) -> httpx.Response:
        capturadas.append(request)
        cuerpo = conteo if request.url.params.get("$select") == "count(*)" else filas
        return httpx.Response(200, json=cuerpo)

    adaptador = DatosGovCoRues(
        transporte=httpx.MockTransport(responder),
        reloj=lambda: datetime(2026, 10, 17, 12, 0, tzinfo=UTC),
        dormir=lambda _s: None,
        costos=CostosEnMemoria(),
        cache=None,
        camaras=CAMARAS,
        tarifas={"computo_seg_usd": 0.000007},
        lote_id=None,
        meta=MetaFuente(
            clave="datos_gov_co_rues",
            proveedor="datos.gov.co",
            paises=frozenset({"CO"}),
            filtros=frozenset({"ciiu", "departamento"}),
            trae=frozenset({"nit", "nombre", "ciiu", "ciudad_camara"}),
            tipo="dataset",
            licencia="CC-BY-SA-4.0",
        ),
    )
    return adaptador, capturadas


def _requests_de_filas(capturadas: list[httpx.Request]) -> list[httpx.Request]:
    # El conteo de naturales (Pulido) es otra request con $select=count(*); acá solo importa la de filas.
    return [r for r in capturadas if r.url.params.get("$select") != "count(*)"]


def _descartables() -> list[dict]:
    validas = _cargar("filas.json")
    return [f for f in _cargar("filas_descartables.json") if f not in validas]


def test_query_filtra_juridicas_en_servidor():
    adaptador, capturadas = _adaptador("filas.json")

    adaptador.buscar(CRITERIOS, 1)

    de_filas = _requests_de_filas(capturadas)
    assert len(de_filas) == 1
    params = de_filas[0].url.params
    where = params["$where"]
    assert where == WHERE_FILAS
    for clausula in (
        "organizacion_juridica != 'PERSONA NATURAL'",
        "organizacion_juridica IS NOT NULL",
        "estado_matricula = 'ACTIVA'",
        "cod_ciiu_act_econ_pri = '4711'",
        "codigo_camara in('04')",
        "nit IS NOT NULL",
    ):
        assert clausula in where, clausula
    assert params["$limit"] == "5000"
    for prohibido in ("$order", "$offset", "$group"):
        assert prohibido not in params, prohibido


def test_select_no_pide_columnas_de_personas():
    adaptador, capturadas = _adaptador("filas.json")

    adaptador.buscar(CRITERIOS, 1)

    de_filas = _requests_de_filas(capturadas)
    assert len(de_filas) == 1
    select = de_filas[0].url.params["$select"]
    assert select == SELECT_FILAS
    columnas = select.split(",")
    for columna in COLUMNAS_DE_PERSONAS:
        assert columna not in columnas, columna


def test_cliente_descarta_lo_que_no_debio_llegar():
    descartables = _descartables()
    assert len(descartables) == 5  # (a), (a'), (b), (c), (d): la fixture no se achicó
    adaptador, _ = _adaptador("filas_descartables.json")

    pagina = adaptador.buscar(CRITERIOS, 1)

    ids = {e.id_fiscal for e in pagina.empresas}
    nombres = {e.nombre for e in pagina.empresas}
    for fila in descartables:
        assert fila.get("nit") not in ids, fila.get("nit")
        assert fila["razon_social"] not in nombres, fila["razon_social"]
    assert len(pagina.empresas) == len(_cargar("filas.json"))
    assert ids == {"999000001", "999000002", "999000003"}
    assert all(e.tipo_titular == "juridica" for e in pagina.empresas)
    # descartados_no_juridica == 5 se suma en T021 (Pulido), cuando el campo exista.


def test_descartados_no_se_loguean(caplog):
    caplog.set_level(logging.DEBUG)  # root: incluye httpx
    secretos = set()
    for fila in _descartables():
        secretos |= {fila.get("nit"), fila["razon_social"]}
    secretos -= {None, ""}
    adaptador, capturadas = _adaptador("filas_descartables.json")

    adaptador.buscar(CRITERIOS, 1)

    # Sin esto, la guarda pasa en vacío con un adaptador que no lee filas.
    assert len(_requests_de_filas(capturadas)) == 1
    for record in caplog.records:
        texto = record.getMessage() + repr(vars(record))
        for secreto in secretos:
            assert secreto not in texto, record.name
