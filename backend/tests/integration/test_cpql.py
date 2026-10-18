"""`v_cpql` (T013, spec 008): CPQL por fuente = costo de la fuente / leads calificados de esa fuente.

Fixture calculada a mano, tenant A (usa `tenants` + `TABLAS_DE_TENANT` del conftest para la limpieza):
- lead1 (jurídica + cumplimiento): encontrado por `osm_overpass` y por `datos_gov_co_rues` (1 lead en las dos
  fuentes), calificado=true.
- lead2 (jurídica + cumplimiento): encontrado solo por `osm_overpass`, calificado=true. No está en `datos_gov_co_rues`:
  por eso `calificados` difiere entre fuentes aunque TOTAL cuenta los dos una sola vez (sin importar en cuántas
  fuentes aparecen).
- lead3 (jurídica + cumplimiento): encontrado solo por `osm_overpass`, con fila en `calificaciones` y
  calificado=false. Tiene que tener la fila: sin ella el JOIN ya lo deja afuera y el filtro `calificado` no se prueba. Prueba que el divisor de `osm_overpass` cuenta calificados (2), no todos los leads de la
  fuente (3): lo que rompe la mutación `cpql_divide_por_todos_los_leads`.
- costos `osm_overpass`: 1 fila gratis (lista 0.10) + 1 fila pagada (lista y real 0.40) -> lista 0.50, real 0.40.
- costos `datos_gov_co_rues`: 1 fila gratis (lista 0.05) + 1 fila pagada (lista y real 0.30) -> lista 0.35, real 0.30.
- costos `croma`: 1 fila pagada (lista y real 0.50), sin lead_fuentes para `croma` -> 0 calificados -> CPQL NULL.
- 1 `dapta_llamada` (fuente NULL): 0.999 (3 min * 0.333). Va a la fila `sin_atribuir` (0 calificados, CPQL NULL),
  como en el tablero: el costo que no cruza con una fuente no desaparece del CPQL.
- 1 costo `evals` (0.70): no entra en ninguna fila, como en el tablero.
- lead2 también encontrado por `sitio_web`, sin costos de esa fuente -> 1 calificado, costo NULL -> CPQL NULL.

TOTAL: costo_lista = 0.50+0.35+0.50+0.999 = 2.349; costo_real = 0.40+0.30+0.50+0.999 = 2.199; calificados = 2
(lead1 y lead2, una vez cada uno aunque lead1 esté en 2 fuentes y osm solo tenga 2 calificados propios).
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db import unidad_de_trabajo

OSM, DATOS_GOV, CROMA = "osm_overpass", "datos_gov_co_rues", "croma"

_INSERT_LEAD = text(
    "INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) VALUES (:id, :t, 'CO', :n, 'juridica')")
_INSERT_CUMPLIMIENTO = text(
    "INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
    "VALUES (:t, :l, 'osm', 'odbl', 'u', now())")
_INSERT_LEAD_FUENTE = text(
    "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
    "VALUES (:t, :l, :b, :f, 'u', 'l')")
_INSERT_CALIFICACION = text(
    "INSERT INTO calificaciones (tenant_id, lead_id, calificado, calificado_en, minutos) "
    "VALUES (:t, :l, :c, now(), :m)")
_INSERT_COSTO = text(
    "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, gratis) "
    "VALUES (:t, :tipo, :u, :cu, 'USD', :p, :f, :g)")
_INSERT_DAPTA = text(
    "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, lead_id, gratis) "
    "VALUES (:t, 'dapta_llamada', 3, '0.333', 'USD', 'dapta', NULL, :l, false)")


@pytest.fixture
def fixture_cpql(admin, tenants):
    tenant = tenants["a"]
    lead1, lead2, lead3 = uuid4(), uuid4(), uuid4()
    busqueda = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:id, :t, 'CO', '{}')"),
                  {"id": busqueda, "t": tenant})
        for lid, n in ((lead1, "L1"), (lead2, "L2"), (lead3, "L3")):
            c.execute(_INSERT_LEAD, {"id": lid, "t": tenant, "n": n})
            c.execute(_INSERT_CUMPLIMIENTO, {"t": tenant, "l": lid})
        for lid, calificado in ((lead1, True), (lead2, True), (lead3, False)):
            c.execute(_INSERT_CALIFICACION, {"t": tenant, "l": lid, "c": calificado, "m": "1"})
        c.execute(_INSERT_LEAD_FUENTE, {"t": tenant, "l": lead1, "b": busqueda, "f": OSM})
        c.execute(_INSERT_LEAD_FUENTE, {"t": tenant, "l": lead1, "b": busqueda, "f": DATOS_GOV})
        c.execute(_INSERT_LEAD_FUENTE, {"t": tenant, "l": lead2, "b": busqueda, "f": OSM})
        c.execute(_INSERT_LEAD_FUENTE, {"t": tenant, "l": lead3, "b": busqueda, "f": OSM})
        c.execute(_INSERT_LEAD_FUENTE, {"t": tenant, "l": lead2, "b": busqueda, "f": "sitio_web"})

        c.execute(_INSERT_COSTO, {"t": tenant, "tipo": "overpass_query", "u": 1, "cu": "0.10", "p": "osm",
                                  "f": OSM, "g": True})
        c.execute(_INSERT_COSTO, {"t": tenant, "tipo": "overpass_query", "u": 1, "cu": "0.40", "p": "osm",
                                  "f": OSM, "g": False})
        c.execute(_INSERT_COSTO, {"t": tenant, "tipo": "socrata_descarga", "u": 1, "cu": "0.05", "p": "datos.gov.co",
                                  "f": DATOS_GOV, "g": True})
        c.execute(_INSERT_COSTO, {"t": tenant, "tipo": "socrata_descarga", "u": 1, "cu": "0.30", "p": "datos.gov.co",
                                  "f": DATOS_GOV, "g": False})
        c.execute(_INSERT_COSTO, {"t": tenant, "tipo": "croma_consulta", "u": 1, "cu": "0.50", "p": "croma",
                                  "f": CROMA, "g": False})
        c.execute(_INSERT_DAPTA, {"t": tenant, "l": lead1})
        c.execute(_INSERT_COSTO, {"t": tenant, "tipo": "llm_tokens_in", "u": 1, "cu": "0.70", "p": "anthropic",
                                  "f": "evals", "g": False})
    return tenant


def _cpql(rt, tenant):
    with unidad_de_trabajo(rt, tenant) as c:
        filas = c.execute(text(
            "SELECT fuente, costo_lista, costo_real, calificados, cpql_lista, cpql_real FROM v_cpql")).all()
    return {f.fuente: f for f in filas}


def test_cpql_por_fuente_es_costo_de_la_fuente_sobre_calificados(rt, fixture_cpql):
    cpql = _cpql(rt, fixture_cpql)

    osm = cpql[OSM]
    assert (osm.calificados, osm.costo_lista, osm.costo_real) == (2, Decimal("0.50"), Decimal("0.40"))
    assert (osm.cpql_lista, osm.cpql_real) == (Decimal("0.25"), Decimal("0.20"))

    datos = cpql[DATOS_GOV]
    assert (datos.calificados, datos.costo_lista, datos.costo_real) == (1, Decimal("0.35"), Decimal("0.30"))
    assert (datos.cpql_lista, datos.cpql_real) == (Decimal("0.35"), Decimal("0.30"))


def test_sin_calificados_cpql_es_null_no_cero(rt, fixture_cpql):
    cpql = _cpql(rt, fixture_cpql)

    croma = cpql[CROMA]
    assert croma.calificados == 0
    assert croma.costo_lista == Decimal("0.50")  # hubo costo, no es que falte la fila
    assert croma.cpql_lista is None and croma.cpql_real is None  # NULL ("sin dato"), nunca 0.50/0


def test_total_incluye_dapta_y_cuenta_leads_distintos(rt, fixture_cpql):
    cpql = _cpql(rt, fixture_cpql)

    total = cpql["TOTAL"]
    # lead1 está en 2 fuentes y lead2 en 1: la suma por fuente de calificados sería 2 (osm) + 1 (datos_gov) = 3,
    # pero TOTAL cuenta leads distintos (2), no filas de lead_fuentes calificadas.
    assert total.calificados == 2
    assert total.costo_lista == Decimal("2.349")  # 0.50 + 0.35 + 0.50 + 0.999 (dapta), fuente NULL incluido
    assert total.costo_real == Decimal("2.199")  # 0.40 + 0.30 + 0.50 + 0.999
    assert total.cpql_lista == Decimal("1.1745") and total.cpql_real == Decimal("1.0995")


def test_sin_atribuir_lleva_el_costo_de_dapta_sin_cpql_propio(rt, fixture_cpql):
    cpql = _cpql(rt, fixture_cpql)

    assert "sin_atribuir" in cpql
    sin_atribuir = cpql["sin_atribuir"]
    assert (sin_atribuir.costo_lista, sin_atribuir.costo_real) == (Decimal("0.999"), Decimal("0.999"))
    assert sin_atribuir.calificados == 0
    assert sin_atribuir.cpql_lista is None and sin_atribuir.cpql_real is None
    assert "evals" not in cpql


def test_la_suma_de_las_filas_es_el_libro_de_costos(rt, fixture_cpql):
    """Ningún costo desaparece del CPQL: Σ filas (sin TOTAL) = Σ `costos` del tenant (sin evals) = TOTAL."""
    cpql = _cpql(rt, fixture_cpql)
    with unidad_de_trabajo(rt, fixture_cpql) as c:
        libro = c.execute(text(
            "SELECT sum(unidades * costo_unitario) AS lista, "
            "sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END) AS real "
            "FROM costos WHERE fuente IS DISTINCT FROM 'evals'")).one()
    filas = [f for fuente, f in cpql.items() if fuente != "TOTAL"]

    assert sum(f.costo_lista for f in filas if f.costo_lista is not None) == libro.lista == cpql["TOTAL"].costo_lista
    assert sum(f.costo_real for f in filas if f.costo_real is not None) == libro.real == cpql["TOTAL"].costo_real


def test_calificados_sin_costo_de_la_fuente_cpql_es_null(rt, fixture_cpql):
    web = _cpql(rt, fixture_cpql)["sitio_web"]

    assert web.calificados == 1
    assert web.costo_lista is None and web.cpql_lista is None and web.cpql_real is None  # sin dato, no 0
