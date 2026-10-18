"""Vistas del libro (spec 005, T007). Fixture de spec:77-112: 10 leads A-J, 2 búsquedas y 2 fuentes, las 9 filas
de `costos` y 2 canales. Se siembra como `postgres` y se lee como `app_rt`, con la RLS puesta.

Los esperados son los de spec:95-112, calculados a mano, y la comparación es exacta: el fixture divide exacto
(las vistas no redondean: solo redondea el front, al mostrar). Cada número se compara contra `Decimal`
construido desde string **y** con `type(valor) is Decimal`, porque `2.0 == Decimal("2")` es `True`: un `::float8`
solo se ve por el tipo (plan §Vistas).

Contrato de columnas que estos tests fijan (spec:334-348):
- `v_tablero_fuentes`: fuente, encontrados, unicos, icp, costo_lista, costo_real, desperdicio_lista,
  desperdicio_real, cpl_lista, cpl_real. `encontrados` y `unicos` cuentan las filas de `lead_fuentes` tal cual
  (006 spec:97: marcar `no_encaja` mueve `icp` y no `encontrados` ni `unicos`); `icp` cuenta los leads del ICP
  (`v_leads_icp`, spec:337), que con este fixture da los mismos números que `unicos`.
- `v_costo_por_lead`: lead_id, fuente, costo_lista, costo_real (costo directo + prorrateo).
- `v_prorrateo`: lote_id, fuente, lead_id, parte_lista, parte_real.
- `v_desperdicio`: fuente, lote_id, desperdicio_lista, desperdicio_real.
- `v_costo_por_canal`: canal, costo_lista, costo_real.
- `v_costo_evals`: lote_id, costo_lista, costo_real.
- `v_costos`: fuente_ef (`COALESCE(fuente, 'sin_atribuir')`), monto_lista, monto_real.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db import unidad_de_trabajo

CS, OSM = "croma_supersociedades_co", "osm_overpass"
SIN_ATRIBUIR, EVALS, TOTAL = "sin_atribuir", "evals", "TOTAL"
D = Decimal

# (lote, fuente) -> leads (spec:89-91). C aparece en las dos fuentes, y dos veces en osm.
LEAD_FUENTES = {
    ("L1", CS): "ABCD", ("L1", OSM): "CEF",
    ("L2", OSM): "CGHIJ",
}

# Las filas de `costos` de spec:77-87: (lote, fuente, letra del lead, canal, unidades, costo_unitario, gratis).
COSTOS = (
    ("L1", CS, None, None, "1", "0.40", True),
    ("L1", CS, None, None, "1", "0.40", False),
    ("L1", OSM, None, None, "3", "0.10", False),
    ("L1", None, None, None, "1", "0.07", False),
    ("L2", CS, None, None, "1", "0.50", False),
    ("L2", OSM, None, None, "4", "0.20", False),
    (None, CS, "A", "email", "1", "0.05", False),
    (None, OSM, "G", "whatsapp", "1", "0.30", False),
    ("E1", EVALS, None, None, "1", "1.00", False),
)
# `tipo` y `proveedor` son de relleno: ninguna vista los lee (la fórmula es unidades × costo_unitario).
TIPO_COSTO = {CS: "croma_consulta", OSM: "overpass_query", None: "web_fetch", EVALS: "llm_tokens_in"}
PROVEEDOR = {CS: "croma", OSM: "osm", None: "datos_gov_co", EVALS: "anthropic"}

INSERT_LEAD_FUENTE = text(
    "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
    "VALUES (:t, :l, :b, :f, 'u', 'l')")
INSERT_COSTO = text(
    "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, canal, lead_id, "
    "lote_id, gratis) VALUES (:t, :tipo, :u, :c, 'USD', :prov, :f, :canal, :lead, :lote, :g)")

COLUMNAS_TABLERO: tuple[str, ...] = ("encontrados", "unicos", "icp", "costo_lista", "costo_real",
                                     "desperdicio_lista", "desperdicio_real", "cpl_lista", "cpl_real")
ENTEROS_TABLERO = ("encontrados", "unicos", "icp")


@pytest.fixture
def fixture10(admin, tenants):
    """Devuelve el tenant A y los ids de sus leads, búsquedas y lotes, para que cada test pueda sembrar más.

    Sin filas de `costos` a propósito: es el fixture de conteos y lo comparte `test_tablero_repo.py`, que
    siembra su propio libro (y tiene tests que exigen el caso "sin costos").
    """
    tenant = tenants["a"]
    lotes = {lote: uuid4() for lote in ("L1", "L2", "E1")}  # E1 no es una búsqueda: es el lote de evals
    busquedas = {lote: lotes[lote] for lote in ("L1", "L2")}
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
    return {"tenant": tenant, "leads": leads, "busquedas": busquedas, "lotes": lotes}


def _parametros_costo(f, lote, fuente, letra, canal, unidades, unitario, gratis):
    return {"t": f["tenant"], "tipo": TIPO_COSTO[fuente], "u": D(unidades), "c": D(unitario),
            "prov": PROVEEDOR[fuente], "f": fuente, "canal": canal,
            "lead": f["leads"][letra] if letra else None, "lote": f["lotes"][lote] if lote else None,
            "g": gratis}


def _costo(admin, f, lote, fuente, letra, unidades, unitario, canal=None, gratis=False):
    """Una fila más en el libro, como `postgres`."""
    with admin.begin() as c:
        c.execute(INSERT_COSTO, _parametros_costo(f, lote, fuente, letra, canal, unidades, unitario, gratis))


@pytest.fixture
def libro(admin, fixture10):
    """`fixture10` más las 9 filas de `costos` de spec:77-87: el libro completo de la spec."""
    with admin.begin() as c:
        for fila in COSTOS:
            c.execute(INSERT_COSTO, _parametros_costo(fixture10, *fila))
    return fixture10


def _filas(rt, tenant, sql, **params):
    with unidad_de_trabajo(rt, tenant) as c:
        return c.execute(text(sql), params).all()


def _letras(f):
    return {lead_id: letra for letra, lead_id in f["leads"].items()}


def _lotes(f):
    return {lote_id: lote for lote, lote_id in f["lotes"].items()}


def _tablero(rt, tenant):
    """(encontrados, unicos) por fuente, tal como lo lee el [MIN]."""
    with unidad_de_trabajo(rt, tenant) as c:
        filas = c.execute(text("SELECT fuente, encontrados, unicos FROM v_tablero_fuentes")).all()
    return {f: (e, u) for f, e, u in filas}


def _tablero_costo(rt, tenant):
    """Toda la fila de `v_tablero_fuentes`, por fuente."""
    filas = _filas(rt, tenant, "SELECT fuente, " + ", ".join(COLUMNAS_TABLERO) + " FROM v_tablero_fuentes")
    return {f[0]: dict(zip(COLUMNAS_TABLERO, f[1:])) for f in filas}


def _costo_por_lead(rt, f):
    """(fuente, letra) -> (costo_lista, costo_real) de `v_costo_por_lead`."""
    letras = _letras(f)
    return {(fuente, letras[lead]): (lista, real)
            for fuente, lead, lista, real in _filas(rt, f["tenant"],
                "SELECT fuente, lead_id, costo_lista, costo_real FROM v_costo_por_lead")}


def _prorrateo(rt, f):
    """(lote, fuente) -> {letra: (parte_lista, parte_real)} de `v_prorrateo`."""
    letras, lotes = _letras(f), _lotes(f)
    partes = {}
    for fuente, lote, lead, lista, real in _filas(rt, f["tenant"],
            "SELECT fuente, lote_id, lead_id, parte_lista, parte_real FROM v_prorrateo"):
        partes.setdefault((lotes[lote], fuente), {})[letras[lead]] = (lista, real)
    return partes


def _desperdicio(rt, f):
    """(lote, fuente) -> (desperdicio_lista, desperdicio_real) de `v_desperdicio`."""
    lotes = _lotes(f)
    return {(lotes[lote], fuente): (lista, real)
            for fuente, lote, lista, real in _filas(rt, f["tenant"],
                "SELECT fuente, lote_id, desperdicio_lista, desperdicio_real FROM v_desperdicio")}


def test_encontrados_y_unicos_por_fuente(rt, fixture10):
    assert _tablero(rt, fixture10["tenant"]) == {CS: (4, 4), OSM: (8, 7), "TOTAL": (12, 10)}


def test_lead_de_dos_fuentes_cuenta_una_vez_en_total(rt, admin, fixture10):
    # A pasa a estar también en osm y K es un lead nuevo: una vista de valores fijos no acierta ningún escenario.
    k = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) "
                       "VALUES (:id, :t, 'CO', 'K', 'juridica')"), {"id": k, "t": fixture10["tenant"]})
        for lead in (fixture10["leads"]["A"], k):
            c.execute(INSERT_LEAD_FUENTE, {"t": fixture10["tenant"], "l": lead,
                                           "b": fixture10["busquedas"]["L2"], "f": OSM})

    tablero = _tablero(rt, fixture10["tenant"])

    unicos = {f: tablero.get(f, (None, None))[1] for f in (CS, OSM, "TOTAL")}
    assert unicos == {CS: 4, OSM: 9, "TOTAL": 11}
    assert tablero.get(OSM) == (10, 9) and tablero.get("TOTAL") == (14, 11)
    assert unicos[CS] + unicos[OSM] == 13  # A y C cuentan en las dos fuentes y una sola vez en el total


def test_cpl_por_fuente_fixture_10_leads(rt, libro):
    """La tabla de spec:97-102, exacta. Los `Decimal` se comparan por valor y por tipo: un `::float8` da rojo."""
    esperado = {
        CS: {"encontrados": 4, "unicos": 4, "icp": 4, "costo_lista": "1.35", "costo_real": "0.95",
             "desperdicio_lista": "0.50", "desperdicio_real": "0.50",
             "cpl_lista": "0.3375", "cpl_real": "0.2375"},
        OSM: {"encontrados": 8, "unicos": 7, "icp": 7, "costo_lista": "1.40", "costo_real": "1.40",
              "desperdicio_lista": "0", "desperdicio_real": "0", "cpl_lista": "0.20", "cpl_real": "0.20"},
        SIN_ATRIBUIR: {"encontrados": 0, "unicos": 0, "icp": 0, "costo_lista": "0.07", "costo_real": "0.07",
                       "desperdicio_lista": "0.07", "desperdicio_real": "0.07", "cpl_lista": None,
                       "cpl_real": None},
        TOTAL: {"encontrados": 12, "unicos": 10, "icp": 10, "costo_lista": "2.82", "costo_real": "2.42",
                "desperdicio_lista": "0.57", "desperdicio_real": "0.57", "cpl_lista": "0.282",
                "cpl_real": "0.242"},
    }

    tablero = _tablero_costo(rt, libro["tenant"])

    assert set(tablero) == set(esperado)
    for fuente, fila in esperado.items():
        for columna, quiero in fila.items():
            valor = tablero[fuente][columna]
            if quiero is None:
                assert valor is None, (fuente, columna, valor)
            elif columna in ENTEROS_TABLERO:
                assert type(valor) is int and valor == quiero, (fuente, columna, valor)
            else:
                assert type(valor) is Decimal and valor == D(quiero), (fuente, columna, valor, quiero)


def test_costo_por_lead_conserva_el_total(rt, libro):
    """spec:104-110 y spec:115: el reparto por lead más el desperdicio reconstruye el libro, por fuente."""
    esperado = {
        (CS, "A"): ("0.25", "0.15"), (CS, "B"): ("0.20", "0.10"),
        (CS, "C"): ("0.20", "0.10"), (CS, "D"): ("0.20", "0.10"),
        (OSM, "C"): ("0.26", "0.26"), (OSM, "E"): ("0.10", "0.10"), (OSM, "F"): ("0.10", "0.10"),
        (OSM, "G"): ("0.46", "0.46"), (OSM, "H"): ("0.16", "0.16"), (OSM, "I"): ("0.16", "0.16"),
        (OSM, "J"): ("0.16", "0.16"),
    }
    del_libro = {CS: ("1.35", "0.95"), OSM: ("1.40", "1.40"), SIN_ATRIBUIR: ("0.07", "0.07")}

    por_lead = _costo_por_lead(rt, libro)
    assert por_lead == {clave: (D(lista), D(real)) for clave, (lista, real) in esperado.items()}

    # El libro crudo, para que la conservación no dependa de la vista que se está probando.
    libro_crudo = {fuente: (lista, real) for fuente, lista, real in _filas(rt, libro["tenant"], """
        SELECT COALESCE(fuente, 'sin_atribuir') AS fuente, sum(unidades * costo_unitario),
               sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END)
        FROM costos WHERE fuente IS DISTINCT FROM 'evals' GROUP BY 1""")}
    assert libro_crudo == {fuente: (D(lista), D(real)) for fuente, (lista, real) in del_libro.items()}

    desperdicio = _desperdicio(rt, libro)
    for fuente, (lista, real) in libro_crudo.items():
        partes = [v for (f, _), v in por_lead.items() if f == fuente]
        repartido = (sum((v[0] for v in partes), D(0)), sum((v[1] for v in partes), D(0)))
        perdido = next((v for (_, f), v in desperdicio.items() if f == fuente), (D(0), D(0)))
        assert (repartido[0] + perdido[0], repartido[1] + perdido[1]) == (lista, real), fuente


def test_lote_sin_leads_es_desperdicio(rt, libro):
    """spec:116: la fila 5 (cs, L2) no tiene leads: es desperdicio y no se reparte entre los leads de L1."""
    assert _desperdicio(rt, libro) == {("L1", SIN_ATRIBUIR): (D("0.07"), D("0.07")),
                                       ("L2", CS): (D("0.50"), D("0.50"))}

    prorrateo = _prorrateo(rt, libro)
    # Sin leads no hay grupo de prorrateo: si la fila 5 se repartiera, aparecería un grupo (L2, cs).
    assert set(prorrateo) == {("L1", CS), ("L1", OSM), ("L2", OSM)}
    # (L1, cs) reparte solo sus 0.80/0.40 (filas 1 y 2): los 0.50 de L2 no entran.
    assert prorrateo[("L1", CS)] == {letra: (D("0.20"), D("0.10")) for letra in "ABCD"}


def test_prorrateo_es_por_lote_y_fuente(rt, libro):
    """spec:117: el costo osm de L2 se reparte entre los 5 leads osm de L2 (0.16), no entre los 8 de L2 ni los de L1."""
    assert _prorrateo(rt, libro) == {
        ("L1", CS): {letra: (D("0.20"), D("0.10")) for letra in "ABCD"},
        ("L1", OSM): {letra: (D("0.10"), D("0.10")) for letra in "CEF"},
        ("L2", OSM): {letra: (D("0.16"), D("0.16")) for letra in "CGHIJ"},
    }


def test_evals_excluido_y_aparte(rt, libro):
    """spec:119: la fila 9 (evals) no entra a ninguna otra vista, y el TOTAL no la incluye."""
    tenant = libro["tenant"]

    assert _filas(rt, tenant, "SELECT lote_id, costo_lista, costo_real FROM v_costo_evals") == [
        (libro["lotes"]["E1"], D("1.00"), D("1.00"))]
    assert {f[0] for f in _filas(rt, tenant, "SELECT DISTINCT fuente_ef FROM v_costos")} == {
        CS, OSM, SIN_ATRIBUIR}
    assert _filas(rt, tenant, "SELECT fuente FROM v_tablero_fuentes WHERE fuente = :f", f=EVALS) == []
    assert _filas(rt, tenant, "SELECT fuente FROM v_desperdicio WHERE fuente = :f", f=EVALS) == []
    assert _filas(rt, tenant, "SELECT canal FROM v_costo_por_canal WHERE canal = :f", f=EVALS) == []

    tablero = _tablero_costo(rt, tenant)
    assert set(tablero) == {CS, OSM, SIN_ATRIBUIR, TOTAL}
    assert (tablero[TOTAL]["costo_lista"], tablero[TOTAL]["costo_real"]) == (D("2.82"), D("2.42"))


def test_fuente_nula_es_sin_atribuir(rt, libro):
    """spec:120: la fila 4 no tiene fuente: da la fila `sin_atribuir`, visible, sin CPL."""
    tenant = libro["tenant"]

    assert {f[0] for f in _filas(rt, tenant, "SELECT DISTINCT fuente_ef FROM v_costos")} == {
        CS, OSM, SIN_ATRIBUIR}

    fila = _tablero_costo(rt, tenant)[SIN_ATRIBUIR]
    assert (fila["encontrados"], fila["unicos"], fila["icp"]) == (0, 0, 0)
    assert (fila["costo_lista"], fila["costo_real"]) == (D("0.07"), D("0.07"))
    assert (fila["desperdicio_lista"], fila["desperdicio_real"]) == (D("0.07"), D("0.07"))
    assert fila["cpl_lista"] is None and fila["cpl_real"] is None
    assert _filas(rt, tenant, "SELECT DISTINCT fuente FROM v_costo_por_lead WHERE fuente = :f",
                  f=SIN_ATRIBUIR) == []


def test_divisor_cero_es_null(rt, libro):
    """spec:121: sin divisor el CPL es NULL, nunca 0 ni un error de división."""
    fila = _tablero_costo(rt, libro["tenant"])[SIN_ATRIBUIR]

    assert fila["icp"] == 0 and fila["costo_lista"] == D("0.07")  # hay costo; lo que falta es el divisor
    assert fila["cpl_lista"] is None and fila["cpl_real"] is None


def test_costo_por_canal(rt, libro):
    """spec:122: solo las filas con canal, y cada canal con su costo."""
    filas = {canal: (lista, real) for canal, lista, real in _filas(rt, libro["tenant"],
             "SELECT canal, costo_lista, costo_real FROM v_costo_por_canal")}

    assert filas == {"email": (D("0.05"), D("0.05")), "whatsapp": (D("0.30"), D("0.30"))}
    assert all(type(valor) is Decimal for par in filas.values() for valor in par)


def test_fila_con_lote_y_lead_va_al_lead(rt, admin, libro):
    """spec:123: lo que define el prorrateo es `lead_id IS NULL`, no `lote_id`: con lote y lead, es del lead."""
    _costo(admin, libro, "L1", CS, "B", "1", "0.05")

    por_lead = _costo_por_lead(rt, libro)
    assert por_lead[(CS, "B")] == (D("0.25"), D("0.15"))  # 0.20/0.10 de prorrateo + 0.05/0.05 directo
    assert por_lead[(CS, "A")] == (D("0.25"), D("0.15"))
    assert por_lead[(CS, "C")] == por_lead[(CS, "D")] == (D("0.20"), D("0.10"))
    assert por_lead[(OSM, "G")] == (D("0.46"), D("0.46"))

    # El prorrateo de (L1, cs) sigue repartiendo sus 0.80/0.40 entre cuatro, como si la fila 10 no existiera.
    assert _prorrateo(rt, libro)[("L1", CS)] == {letra: (D("0.20"), D("0.10")) for letra in "ABCD"}


def test_lead_fusionado_no_cuenta(rt, admin, libro):
    """spec:124, con el filtro de ICP de spec:337. H absorbido por G: deja de contar como ICP y, una vez movidos
    sus `lead_fuentes`, tampoco en los conteos del tablero. El primer paso deja a H con filas a propósito: es el
    estado en el que el filtro `fusionado_en IS NULL` de `v_leads_icp` es el que decide (y el único donde el
    absorbido puede reaparecer si el filtro falta)."""
    tenant, h, g = libro["tenant"], libro["leads"]["H"], libro["leads"]["G"]
    with admin.begin() as c:
        c.execute(text("UPDATE leads SET fusionado_en = :g WHERE id = :h"), {"g": g, "h": h})

    # 1) absorbido, todavía con sus filas: fuera del ICP; el tablero aún lo ve como lead encontrado.
    assert _filas(rt, tenant, "SELECT count(*), count(DISTINCT lead_id) FROM v_leads_icp WHERE fuente = :f",
                  f=OSM) == [(7, 6)]
    assert _prorrateo(rt, libro)[("L2", OSM)] == {letra: (D("0.20"), D("0.20")) for letra in "CGIJ"}
    fila = _tablero_costo(rt, tenant)[OSM]
    assert (fila["encontrados"], fila["unicos"], fila["icp"]) == (8, 7, 6)

    # 2) movidos sus `lead_fuentes` a G: la fila (G, osm, L2) ya existe, así que la de H se descarta.
    with admin.begin() as c:
        c.execute(text("DELETE FROM lead_fuentes WHERE lead_id = :h"), {"h": h})

    fila = _tablero_costo(rt, tenant)[OSM]
    assert (fila["encontrados"], fila["unicos"], fila["icp"]) == (7, 6, 6)
    assert (fila["costo_lista"], fila["costo_real"]) == (D("1.40"), D("1.40"))
    assert _prorrateo(rt, libro)[("L2", OSM)] == {letra: (D("0.20"), D("0.20")) for letra in "CGIJ"}
    total = _tablero_costo(rt, tenant)[TOTAL]
    assert (total["encontrados"], total["unicos"], total["icp"]) == (11, 9, 9)
