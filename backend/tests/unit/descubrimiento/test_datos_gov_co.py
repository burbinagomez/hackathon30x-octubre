import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.descubrimiento.aplicacion.camaras import cargar_camaras
from app.modulos.descubrimiento.dominio.errores import (
    CriterioNoSoportado,
    FuenteNoDisponible,
)
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
CUERPO_SECRETO = "CUERPO-SECRETO"
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


AHORA = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class RelojFalso:
    def __init__(self) -> None:
        self.t = AHORA

    def __call__(self) -> datetime:
        return self.t

    def avanzar(self, segundos: float) -> None:
        self.t += timedelta(seconds=segundos)


def _transporte_fijo(
    filas: list[dict], cabeceras: dict[str, str] | None, capturadas: list[httpx.Request]
) -> httpx.MockTransport:
    conteo = _cargar("conteo_naturales.json")

    def responder(request: httpx.Request) -> httpx.Response:
        capturadas.append(request)
        cuerpo = conteo if request.url.params.get("$select") == "count(*)" else filas
        return httpx.Response(200, json=cuerpo, headers=cabeceras)

    return httpx.MockTransport(responder)


def _transporte_guionado(
    reloj: RelojFalso,
    pasos: list[tuple[int | str, float]],
    capturadas: list[httpx.Request],
) -> httpx.MockTransport:
    """Cada paso es (status | "timeout", segundos que tarda la request según el reloj)."""
    restantes = list(pasos)

    def responder(request: httpx.Request) -> httpx.Response:
        capturadas.append(request)
        estado, segundos = restantes.pop(0)
        reloj.avanzar(segundos)
        if estado == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if estado != 200:
            return httpx.Response(int(estado), text=CUERPO_SECRETO)
        return httpx.Response(200, json=_cargar("filas.json"))

    return httpx.MockTransport(responder)


def _adaptador(
    fixture_filas: str = "filas.json",
    *,
    cabeceras: dict[str, str] | None = None,
    pasos: list[tuple[int | str, float]] | None = None,
    lote_id: UUID | None = None,
) -> tuple[DatosGovCoRues, list[httpx.Request]]:
    capturadas: list[httpx.Request] = []
    reloj = RelojFalso()
    if pasos is None:
        transporte = _transporte_fijo(_cargar(fixture_filas), cabeceras, capturadas)
    else:
        transporte = _transporte_guionado(reloj, pasos, capturadas)

    adaptador = DatosGovCoRues(
        transporte=transporte,
        reloj=reloj,
        dormir=lambda _s: None,
        costos=CostosEnMemoria(),
        cache=None,
        camaras=CAMARAS,
        tarifas={"computo_seg_usd": 0.000007},
        lote_id=lote_id,
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


def _criterios(**filtros: str | tuple[str, ...]) -> CriteriosICP:
    return CriteriosICP(
        pais="CO", filtros={"ciiu": "4711", "departamento": "11", **filtros}
    )


def test_departamento_25_se_traduce_a_cuatro_camaras():
    adaptador, capturadas = _adaptador()

    adaptador.buscar(_criterios(departamento="25"), 1)

    where = _requests_de_filas(capturadas)[0].url.params["$where"]
    assert "codigo_camara in('04','14','47','58')" in where


@pytest.mark.parametrize(
    "filtros",
    [
        {"departamento": "99"},  # fuera del YAML
        {"ciiu": "47' OR '1'='1"},  # inyección SoQL
        {"ciiu": "471"},
        {"ciiu": "47111"},
        {"ciiu": ("4711", "4712")},  # tupla: varios valores no se soportan
    ],
)
def test_criterio_invalido_lanza_sin_requests(filtros):
    adaptador, capturadas = _adaptador()

    with pytest.raises(CriterioNoSoportado):
        adaptador.buscar(_criterios(**filtros), 1)

    assert capturadas == []


def test_mapea_fila_a_empresa_cruda():
    adaptador, _ = _adaptador()

    pagina = adaptador.buscar(CRITERIOS, 1)

    alfa = next(e for e in pagina.empresas if e.id_fiscal == "999000001")
    assert alfa.nombre == "EJEMPLO FICTICIO ALFA S.A.S."
    assert alfa.pais == "CO"
    assert alfa.ciudad == "Bogotá"
    assert alfa.actividad == ("4711", "CIIU")
    assert alfa.tipo_titular == "juridica"
    assert alfa.fuente == "datos_gov_co_rues"
    assert (
        alfa.url_origen
        == "https://www.datos.gov.co/resource/c82u-588k.json?nit=999000001"
    )
    assert alfa.direccion is None
    assert alfa.web is None
    assert (
        adaptador.meta.licencia == "CC-BY-SA-4.0"
    )  # la licencia va en meta, no en EmpresaCruda (D4)


def test_as_of_sale_del_header():
    adaptador, _ = _adaptador(
        cabeceras={"X-SODA2-Truth-Last-Modified": "Fri, 02 Oct 2026 21:39:26 GMT"}
    )

    pagina = adaptador.buscar(CRITERIOS, 1)

    assert {e.as_of for e in pagina.empresas} == {
        datetime(2026, 10, 2, 21, 39, 26, tzinfo=UTC)
    }


def test_as_of_sin_header_es_la_hora_del_reloj():
    adaptador, _ = _adaptador()

    pagina = adaptador.buscar(CRITERIOS, 1)

    assert {e.as_of for e in pagina.empresas} == {AHORA}


def test_pagina_2_vacia_sin_request():
    adaptador, capturadas = _adaptador()

    pagina = adaptador.buscar(CRITERIOS, 2)

    assert pagina.empresas == ()
    assert capturadas == []
    assert adaptador._costos.filas == []


LOTE = UUID("00000000-0000-4000-8000-000000000011")
ROJO_T029 = pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="rojo T029; verde en T030"
)


def _buscar_sin_propagar(
    adaptador: DatosGovCoRues,
) -> httpx.HTTPError | FuenteNoDisponible | None:
    """Devuelve la excepción en vez de propagarla: así el rojo es un assert y no un error de la fuente."""
    try:
        adaptador.buscar(CRITERIOS, 1)
    except (httpx.HTTPError, FuenteNoDisponible) as exc:
        return exc
    return None


@ROJO_T029
def test_registra_segundos_de_cada_intento():
    adaptador, capturadas = _adaptador(pasos=[(503, 2), (200, 3)], lote_id=LOTE)

    error = _buscar_sin_propagar(adaptador)

    filas = adaptador._costos.filas
    assert [f.unidades for f in filas] == [Decimal(2), Decimal(3)]
    assert error is None
    assert len(_requests_de_filas(capturadas)) == 2
    for fila in filas:
        assert fila.tipo == "socrata_descarga"
        assert fila.costo_unitario == Decimal(str(0.000007))
        assert fila.proveedor == "datos.gov.co"
        assert fila.fuente == "datos_gov_co_rues"
        assert fila.gratis is False
        assert fila.lead_id is None
        assert fila.lote_id == LOTE
    # La tercera fila (conteo de naturales, 1 s) se suma en T021 (Pulido).


@ROJO_T029
@pytest.mark.parametrize("fallo", [503, "timeout"])
def test_segundo_fallo_lanza_fuente_no_disponible(fallo):
    adaptador, capturadas = _adaptador(pasos=[(fallo, 2), (fallo, 3)])

    error = _buscar_sin_propagar(adaptador)

    assert isinstance(error, FuenteNoDisponible)
    assert CUERPO_SECRETO not in str(error)
    assert len(adaptador._costos.filas) == 2
    assert (
        len(capturadas) == 2
    )  # ninguna request de conteo (T021 suma el assert propio)
