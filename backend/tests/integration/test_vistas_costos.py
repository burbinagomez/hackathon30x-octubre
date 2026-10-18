"""Vistas del libro (spec 005). Fixture de spec:77-112: 10 leads A-J, 2 fuentes. Se siembra como postgres y se lee como app_rt."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db import unidad_de_trabajo

CS, OSM = "croma_supersociedades_co", "osm_overpass"
# (lote, fuente) -> leads (spec:95-98). C aparece en las dos fuentes, y dos veces en osm.
LEAD_FUENTES = {
    ("L1", CS): "ABCD", ("L1", OSM): "CEF",
    ("L2", OSM): "CGHIJ",
}
INSERT_LEAD_FUENTE = text(
    "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
    "VALUES (:t, :l, :b, :f, 'u', 'l')")


@pytest.fixture
def fixture10(admin, tenants):
    """Devuelve el tenant A y los ids de sus leads y búsquedas, para que cada test pueda sembrar más."""
    tenant = tenants["a"]
    busquedas = {lote: uuid4() for lote in ("L1", "L2")}
    leads = {letra: uuid4() for letra in "ABCDEFGHIJ"}
    with admin.begin() as c:
        for bid in busquedas.values():
            c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:id, :t, 'CO', '{}')"),
                      {"id": bid, "t": tenant})
        for letra, lid in leads.items():
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) "
                           "VALUES (:id, :t, 'CO', :n, 'juridica')"), {"id": lid, "t": tenant, "n": letra})
        for (lote, fuente), letras in LEAD_FUENTES.items():
            for letra in letras:
                c.execute(INSERT_LEAD_FUENTE,
                          {"t": tenant, "l": leads[letra], "b": busquedas[lote], "f": fuente})
    return {"tenant": tenant, "leads": leads, "busquedas": busquedas}


def _tablero(rt, tenant):
    with unidad_de_trabajo(rt, tenant) as c:
        filas = c.execute(text("SELECT fuente, encontrados, unicos FROM v_tablero_fuentes")).all()
    return {f: (e, u) for f, e, u in filas}


def test_encontrados_y_unicos_por_fuente(rt, fixture10):
    assert _tablero(rt, fixture10["tenant"]) == {CS: (4, 4), OSM: (8, 7), "TOTAL": (12, 10)}


def test_lead_de_dos_fuentes_cuenta_una_vez_en_total(rt, admin, fixture10):
    # A pasa a estar también en osm: ya no es solo de cs. Una vista de valores fijos no puede acertar los dos escenarios.
    with admin.begin() as c:
        c.execute(INSERT_LEAD_FUENTE, {"t": fixture10["tenant"], "l": fixture10["leads"]["A"],
                                       "b": fixture10["busquedas"]["L2"], "f": OSM})

    tablero = _tablero(rt, fixture10["tenant"])

    unicos = {f: tablero.get(f, (None, None))[1] for f in (CS, OSM, "TOTAL")}
    assert unicos == {CS: 4, OSM: 8, "TOTAL": 10}
    assert tablero.get(OSM) == (9, 8) and tablero.get("TOTAL") == (13, 10)
    assert unicos[CS] + unicos[OSM] == 12  # A y C cuentan en las dos fuentes y una sola vez en el total
