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


@pytest.fixture
def fixture10(admin_engine):
    tenant = uuid4()
    busquedas = {lote: uuid4() for lote in ("L1", "L2")}
    leads = {letra: uuid4() for letra in "ABCDEFGHIJ"}
    with admin_engine.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:t, 'T')"), {"t": tenant})
        for lote, bid in busquedas.items():
            c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:id, :t, 'CO', '{}')"),
                      {"id": bid, "t": tenant})
        for letra, lid in leads.items():
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) "
                           "VALUES (:id, :t, 'CO', :n, 'juridica')"), {"id": lid, "t": tenant, "n": letra})
        for (lote, fuente), letras in LEAD_FUENTES.items():
            for letra in letras:
                c.execute(text("INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                               "VALUES (:t, :l, :b, :f, 'u', 'l')"),
                          {"t": tenant, "l": leads[letra], "b": busquedas[lote], "f": fuente})
    yield tenant
    with admin_engine.begin() as c:
        for tabla in ("lead_fuentes", "leads", "busquedas"):
            c.execute(text(f"DELETE FROM {tabla} WHERE tenant_id = :t"), {"t": tenant})
        c.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tenant})


def _tablero(rt_engine, tenant):
    with unidad_de_trabajo(rt_engine, tenant) as c:
        filas = c.execute(text("SELECT fuente, encontrados, unicos FROM v_tablero_fuentes")).all()
    return {f: (e, u) for f, e, u in filas}


def test_encontrados_y_unicos_por_fuente(rt_engine, fixture10):
    assert _tablero(rt_engine, fixture10) == {CS: (4, 4), OSM: (8, 7), "TOTAL": (12, 10)}


def test_lead_de_dos_fuentes_cuenta_una_vez_en_total(rt_engine, fixture10):
    tablero = _tablero(rt_engine, fixture10)
    assert tablero[CS][1] + tablero[OSM][1] == 11  # C cuenta en las dos fuentes...
    assert tablero["TOTAL"][1] == 10  # ...y una sola vez en el total
