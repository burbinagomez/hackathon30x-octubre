"""Tablero: costo y CPL por fuente (spec 005, T042). Fixture de 10 leads de spec:74-112, sembrado como postgres y leído
como app_rt con el tenant del token. Los números son los de la tabla de la spec, calculados a mano."""
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from app.modulos.tablero.infraestructura.persistencia.repositorio_tablero import leer_tablero
from tests.integration.test_vistas_costos import CS, OSM, fixture10  # noqa: F401  (fixture)

INSERT_COSTO = text(
    "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, canal, lead_id, "
    "lote_id, gratis) VALUES (:t, 'croma_consulta', :u, :c, 'USD', 'p', :f, :canal, :lead, :lote, :g)")


def _costo(c, tenant, lote, fuente, unidades, unitario, gratis=False, lead=None, canal=None):
    c.execute(INSERT_COSTO, {"t": tenant, "lote": lote, "f": fuente, "u": unidades, "c": unitario, "g": gratis,
                             "lead": lead, "canal": canal})


def sembrar_costos(admin, f):
    """Las filas 1-9 de la spec."""
    t, b, leads = f["tenant"], f["busquedas"], f["leads"]
    with admin.begin() as c:
        _costo(c, t, b["L1"], CS, 1, "0.40", gratis=True)
        _costo(c, t, b["L1"], CS, 1, "0.40")
        _costo(c, t, b["L1"], OSM, 3, "0.10")
        _costo(c, t, b["L1"], None, 1, "0.07")
        _costo(c, t, b["L2"], CS, 1, "0.50")
        _costo(c, t, b["L2"], OSM, 4, "0.20")
        _costo(c, t, None, CS, 1, "0.05", lead=leads["A"], canal="email")
        _costo(c, t, None, OSM, 1, "0.30", lead=leads["G"], canal="whatsapp")
        _costo(c, t, uuid4(), "evals", 1, "1.00")


def _filas(datos):
    return {f.fuente: f for f in (*datos.fuentes, datos.total)}


def test_cpl_por_fuente_fixture_10_leads(rt, admin, fixture10):
    sembrar_costos(admin, fixture10)

    datos = leer_tablero(rt, fixture10["tenant"])

    filas = _filas(datos)
    esperado = {  # fuente: (encontrados, unicos, costo_lista, costo_real, cpl_lista, cpl_real)
        CS: (4, 4, "1.35", "0.95", "0.3375", "0.2375"),
        OSM: (8, 7, "1.40", "1.40", "0.20", "0.20"),
        "sin_atribuir": (0, 0, "0.07", "0.07", None, None),
        "TOTAL": (12, 10, "2.82", "2.42", "0.282", "0.242"),
    }
    assert set(filas) == set(esperado)
    for fuente, (enc, uni, lista, real, cpl_l, cpl_r) in esperado.items():
        f = filas[fuente]
        assert (f.encontrados, f.unicos) == (enc, uni), fuente
        for valor, quiero in ((f.costo_lista, lista), (f.costo_real, real), (f.cpl_lista, cpl_l), (f.cpl_real, cpl_r)):
            if quiero is None:
                assert valor is None, fuente  # divisor cero: null, nunca 0
            else:
                assert type(valor) is Decimal and valor == Decimal(quiero), (fuente, valor, quiero)


def test_cpl_usa_unicos_y_no_encontrados(rt, admin, fixture10):
    sembrar_costos(admin, fixture10)
    # osm: 1.40 / 7 únicos = 0.20; con los 8 encontrados daría 0.175.
    assert _filas(leer_tablero(rt, fixture10["tenant"]))[OSM].cpl_lista == Decimal("0.20")


def test_costo_de_evals_va_aparte_y_no_entra_al_total(rt, admin, fixture10):
    sembrar_costos(admin, fixture10)

    datos = leer_tablero(rt, fixture10["tenant"])

    assert datos.costo_evals == Decimal("1.00")
    assert "evals" not in _filas(datos)
    assert datos.total.costo_lista == Decimal("2.82")


def test_sin_costos_el_costo_y_el_cpl_son_null(rt, fixture10):
    datos = leer_tablero(rt, fixture10["tenant"])

    assert datos.costo_evals is None
    for f in (*datos.fuentes, datos.total):
        assert (f.costo_lista, f.costo_real, f.cpl_lista, f.cpl_real) == (None, None, None, None), f.fuente


def test_costos_sin_leads_dan_total_con_cpl_null(rt, admin, tenants):
    with admin.begin() as c:
        _costo(c, tenants["a"], uuid4(), CS, 1, "0.50")

    datos = leer_tablero(rt, tenants["a"])

    assert [(f.fuente, f.unicos, f.costo_lista, f.cpl_lista) for f in datos.fuentes] == [(CS, 0, Decimal("0.50"), None)]
    assert (datos.total.unicos, datos.total.costo_lista, datos.total.cpl_lista) == (0, Decimal("0.50"), None)


def test_costos_de_otro_tenant_no_cuentan(rt, admin, fixture10, tenants):
    sembrar_costos(admin, fixture10)
    with admin.begin() as c:
        _costo(c, tenants["b"], uuid4(), CS, 100, "9.99")
        _costo(c, tenants["b"], uuid4(), "evals", 100, "9.99")

    como_a = leer_tablero(rt, fixture10["tenant"])
    como_b = leer_tablero(rt, tenants["b"])

    assert _filas(como_a)[CS].costo_lista == Decimal("1.35") and como_a.costo_evals == Decimal("1.00")
    assert [f.fuente for f in como_b.fuentes] == [CS]  # B solo ve lo suyo
    assert _filas(como_b)[CS].costo_lista == Decimal("999.00")


def test_costo_de_intake_va_aparte_y_no_entra_ni_a_las_fuentes_ni_al_total(rt, admin, fixture10):
    sembrar_costos(admin, fixture10)
    with admin.begin() as c:  # la Puerta B: lead_id NULL, un lote por corrida, fuente='intake'
        lote = uuid4()
        _costo(c, fixture10["tenant"], lote, "intake", 200, "0.0000001")
        _costo(c, fixture10["tenant"], lote, "intake", 60, "0.0000005")

    datos = leer_tablero(rt, fixture10["tenant"])

    assert datos.costo_intake == Decimal("0.000050")
    assert datos.costo_evals == Decimal("1.00")  # cada categoría por su lado
    assert "intake" not in _filas(datos)
    assert datos.total.costo_lista == Decimal("2.82") and datos.total.costo_real == Decimal("2.42")
    assert datos.total.cpl_lista == Decimal("0.282")


def test_sin_costos_de_intake_es_null_y_no_cero(rt, fixture10):
    assert leer_tablero(rt, fixture10["tenant"]).costo_intake is None


def test_costo_de_intake_de_otro_tenant_no_cuenta(rt, admin, tenants):
    with admin.begin() as c:
        _costo(c, tenants["b"], uuid4(), "intake", 100, "9.99")

    assert leer_tablero(rt, tenants["a"]).costo_intake is None
    assert leer_tablero(rt, tenants["b"]).costo_intake == Decimal("999.00")
