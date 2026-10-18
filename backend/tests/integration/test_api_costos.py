"""GET /costos: libro de costos de solo lectura, por tenant y bajo RLS. Sin token: lo cubre test_auth.
Datos sintéticos, sembrados como postgres; la API lee como app_rt."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

CLAVES = {"ts", "tipo", "fuente", "proveedor", "cantidad", "costo_usd", "gratis", "busqueda_id", "lote_id", "lead"}
BASE = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _fila(admin, tenant, n, tipo="overpass_query", fuente="osm_overpass", unidades="1", unitario="0.5", lote=None,
          lead=None, gratis=False):
    with admin.begin() as c:
        c.execute(text(
            "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, lead_id, lote_id, "
            "gratis, ts) VALUES (:t, :tipo, :u, :c, 'USD', 'prov', :f, :lead, :lote, :g, :ts)"),
            {"t": tenant, "tipo": tipo, "u": unidades, "c": unitario, "f": fuente, "lead": lead, "lote": lote, "g": gratis,
             "ts": BASE + timedelta(minutes=n)})


@pytest.fixture
def datos(cliente, usuarios, admin):
    a, b = usuarios["tenant_a"], usuarios["tenant_b"]
    lote, lead = uuid4(), uuid4()
    _fila(admin, a, 1, lote=lote)                                                  # 0.5
    _fila(admin, a, 2, tipo="croma_consulta", fuente="croma_supersociedades_co", unidades="2", unitario="0.25",
          lote=lote, gratis=True)                                                  # 0.5 lista, 0 real
    _fila(admin, a, 3, tipo="web_fetch", fuente="sitio_web", unidades="4", unitario="0.125", lead=lead)  # 0.5
    _fila(admin, b, 4, unidades="100", unitario="1")                               # ajena: 100
    return {"api": cliente, "u": usuarios, "lote": lote, "lead": lead}


def _get(d, quien="a", **query):
    return d["api"].get("/costos", params=query, headers=_bearer(d["u"][quien]))


def test_filas_propias_por_ts_descendente_sin_las_de_otro_tenant(datos):
    r = _get(datos)

    assert r.status_code == 200
    cuerpo = r.json()
    assert [f["tipo"] for f in cuerpo["items"]] == ["web_fetch", "croma_consulta", "overpass_query"]
    assert cuerpo["total"] == 3 and cuerpo["pagina"] == 1 and cuerpo["tamano"] == 50
    assert all(set(f) == CLAVES for f in cuerpo["items"])
    ultima = cuerpo["items"][2]
    assert (ultima["fuente"], ultima["proveedor"], ultima["cantidad"], ultima["costo_usd"]) == (
        "osm_overpass", "prov", "1", "0.5")
    assert ultima["lote_id"] == ultima["busqueda_id"] == str(datos["lote"])


def test_otro_tenant_ve_solo_lo_suyo(datos):
    cuerpo = _get(datos, "b").json()

    assert [f["costo_usd"] for f in cuerpo["items"]] == ["100"]
    assert cuerpo["total_usd"] == "100"


def test_subtotales_por_tipo_y_por_fuente(datos):
    cuerpo = _get(datos).json()

    assert Decimal(cuerpo["total_usd"]) == Decimal("1.5")
    assert Decimal(cuerpo["total_real_usd"]) == Decimal("1.0")  # la fila gratis suma a lista, no a real
    assert {s["tipo"]: Decimal(s["costo_usd"]) for s in cuerpo["por_tipo"]} == {
        "overpass_query": Decimal("0.5"), "croma_consulta": Decimal("0.5"), "web_fetch": Decimal("0.5")}
    assert {s["fuente"]: Decimal(s["costo_usd"]) for s in cuerpo["por_fuente"]} == {
        "osm_overpass": Decimal("0.5"), "croma_supersociedades_co": Decimal("0.5"), "sitio_web": Decimal("0.5")}


def test_lead_es_solo_booleano_nunca_el_id(datos):
    r = _get(datos)

    assert str(datos["lead"]) not in r.text and "lead_id" not in r.text
    por_tipo = {f["tipo"]: f for f in r.json()["items"]}
    assert por_tipo["web_fetch"]["lead"] is True
    assert por_tipo["overpass_query"]["lead"] is False


def test_paginacion_de_50_y_totales_de_todo_el_libro(datos, admin, usuarios):
    for n in range(10, 70):  # 60 filas más de 1 USD en una fuente nueva
        _fila(admin, usuarios["tenant_a"], n, fuente="otra", unidades="1", unitario="1")

    p1, p2, p3 = (_get(datos, pagina=n).json() for n in (1, 2, 3))

    assert (len(p1["items"]), len(p2["items"]), len(p3["items"])) == (50, 13, 0)
    assert p1["total"] == 63 and p2["pagina"] == 2
    assert Decimal(p1["total_usd"]) == Decimal(p2["total_usd"]) == Decimal("61.5")  # no solo la página
    ts = [f["ts"] for f in p1["items"] + p2["items"]]
    assert ts == sorted(ts, reverse=True)


def test_filtro_por_busqueda_acota_filas_y_totales(datos):
    cuerpo = _get(datos, busqueda_id=str(datos["lote"])).json()

    assert cuerpo["total"] == 2
    assert {f["tipo"] for f in cuerpo["items"]} == {"overpass_query", "croma_consulta"}
    assert Decimal(cuerpo["total_usd"]) == Decimal("1.0")
    assert [s["tipo"] for s in cuerpo["por_tipo"]].count("web_fetch") == 0


def test_filtro_con_busqueda_ajena_o_inexistente_da_vacio(datos):
    cuerpo = _get(datos, busqueda_id=str(uuid4())).json()

    assert cuerpo["items"] == [] and cuerpo["total"] == 0 and cuerpo["total_usd"] == "0"


def test_parametros_invalidos_son_422(datos):
    assert _get(datos, pagina=0).status_code == 422
    assert _get(datos, busqueda_id="no-es-uuid").status_code == 422
