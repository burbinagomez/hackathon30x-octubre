"""Embudo por fuente del tablero: enriquecidos, contactables, con teléfono y calificados (solo conteos).
Sobre el fixture de 10 leads (A-J): CS = A,B,C,D; OSM = C,E,F,G,H,I,J; C está en las dos fuentes."""
from uuid import uuid4

from sqlalchemy import text

from app.modulos.tablero.infraestructura.persistencia.repositorio_tablero import leer_tablero
from tests.integration.test_tablero_repo import _costo
from tests.integration.test_vistas_costos import CS, OSM, INSERT_LEAD_FUENTE, fixture10  # noqa: F401  (fixture)

CIFRADO = b"x" * 40  # solo el largo importa para el CHECK; no es un dato real


def _enriquecer(admin, f, letra, *, contactable, razon=None, telefono=False, calificado=None, natural=False):
    p = {"id": f["leads"][letra], "t": f["tenant"], "c": contactable, "r": razon, "cif": CIFRADO}
    with admin.begin() as c:
        c.execute(text(
            "UPDATE leads SET enriquecido_en = now(), contactable = :c, razon_no_contactable = :r, "
            "telefono_cifrado = CASE WHEN :tel THEN :cif END, telefono_canal = CASE WHEN :tel THEN 'sitio_web' END "
            "WHERE id = :id AND tenant_id = :t"), {**p, "tel": telefono})
        if natural:
            c.execute(text("UPDATE leads SET tipo_titular = 'natural', nombre = NULL, nombre_cifrado = :cif "
                           "WHERE id = :id AND tenant_id = :t"), p)
        if calificado is not None:
            c.execute(text("INSERT INTO calificaciones (tenant_id, lead_id, calificado, calificado_en, minutos) "
                           "VALUES (:t, :id, :k, now(), 1)"), {**p, "k": calificado})


def sembrar_embudo(admin, f):
    _enriquecer(admin, f, "A", contactable=True, telefono=True, calificado=True)
    _enriquecer(admin, f, "B", contactable=False, razon="sin_canal_publicado")
    _enriquecer(admin, f, "C", contactable=True, telefono=True, calificado=True)
    _enriquecer(admin, f, "E", contactable=True)  # contactable por email: sin teléfono
    _enriquecer(admin, f, "F", contactable=True, telefono=True, calificado=False)
    # Natural con teléfono cifrado: no cuenta como "con teléfono" (solo jurídicas).
    _enriquecer(admin, f, "G", contactable=False, razon="persona_natural", telefono=True, natural=True)


def _filas(datos):
    return {f.fuente: f for f in (*datos.fuentes, datos.total)}


def _embudo(f):
    return (f.encontrados, f.unicos, f.enriquecidos, f.contactables, f.con_telefono, f.calificados)


def test_embudo_por_fuente_con_datos_sembrados(rt, admin, fixture10):
    sembrar_embudo(admin, fixture10)

    filas = _filas(leer_tablero(rt, fixture10["tenant"]))

    assert _embudo(filas[CS]) == (4, 4, 3, 2, 2, 2)
    assert _embudo(filas[OSM]) == (8, 7, 4, 3, 2, 1)


def test_lead_de_dos_fuentes_cuenta_en_las_dos_y_una_vez_en_el_total(rt, admin, fixture10):
    sembrar_embudo(admin, fixture10)

    filas = _filas(leer_tablero(rt, fixture10["tenant"]))

    # C (enriquecido, contactable, con teléfono, calificado) suma en CS y en OSM; el total lo cuenta una vez.
    assert _embudo(filas["TOTAL"]) == (12, 10, 6, 4, 3, 2)
    assert filas[CS].calificados + filas[OSM].calificados == 3 != filas["TOTAL"].calificados


def test_sin_enriquecimiento_los_conteos_son_ceros_reales(rt, fixture10):
    filas = _filas(leer_tablero(rt, fixture10["tenant"]))

    for fuente in (CS, OSM, "TOTAL"):
        f = filas[fuente]
        assert (f.enriquecidos, f.contactables, f.con_telefono, f.calificados) == (0, 0, 0, 0), fuente


def test_costo_sin_fuente_no_inventa_embudo(rt, admin, fixture10):
    with admin.begin() as c:
        _costo(c, fixture10["tenant"], uuid4(), None, 1, "0.07")

    sin = _filas(leer_tablero(rt, fixture10["tenant"]))["sin_atribuir"]

    assert (sin.enriquecidos, sin.contactables, sin.con_telefono, sin.calificados) == (None, None, None, None)


def test_el_embudo_de_otro_tenant_no_se_ve(rt, admin, fixture10, tenants):
    sembrar_embudo(admin, fixture10)
    b, lead_b, busqueda_b = tenants["b"], uuid4(), uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:id, :t, 'CO', '{}')"),
                  {"id": busqueda_b, "t": b})
        c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular, enriquecido_en, contactable) "
                       "VALUES (:id, :t, 'CO', 'Z', 'juridica', now(), true)"), {"id": lead_b, "t": b})
        c.execute(INSERT_LEAD_FUENTE, {"t": b, "l": lead_b, "b": busqueda_b, "f": CS})
        c.execute(text("INSERT INTO calificaciones (tenant_id, lead_id, calificado, calificado_en, minutos) "
                       "VALUES (:t, :l, true, now(), 1)"), {"t": b, "l": lead_b})

    como_a = _filas(leer_tablero(rt, fixture10["tenant"]))
    como_b = _filas(leer_tablero(rt, b))

    assert _embudo(como_a[CS]) == (4, 4, 3, 2, 2, 2)  # nada de B
    assert _embudo(como_b[CS]) == (1, 1, 1, 1, 0, 1)
    assert set(como_b) == {CS, "TOTAL"}
