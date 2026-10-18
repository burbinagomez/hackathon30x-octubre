"""Tabla contactos y sus dos vistas (spec 007, plan.md §DDL). Se siembra como postgres y se lee como app_rt."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import unidad_de_trabajo

VISTAS = ["v_leads_con_opt_out", "v_tasa_respuesta_canal"]
UNIQUE_VIOLADO = "23505"
INSERT_CONTACTO = text(
    "INSERT INTO contactos (tenant_id, lead_id, busqueda_id, canal, asunto, cuerpo, estado, enviado_en, respondio_en) "
    "VALUES (:t, :l, :b, 'email', 'a', 'c', :estado, :enviado, :respondio)")


@pytest.fixture
def sembrado(admin, tenants):
    """Tenant A con una búsqueda y tres leads; devuelve sus ids."""
    ids = {"t": tenants["a"], "b": uuid4(), "leads": [uuid4() for _ in range(3)]}
    with admin.begin() as c:
        c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:b, :t, 'CO', '{}')"), ids)
        for lead in ids["leads"]:
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) "
                           "VALUES (:l, :t, 'CO', 'x', 'juridica')"), {"l": lead, "t": ids["t"]})
    return ids


def _contacto(c, ids, lead, estado="aprobado", enviado=False, respondio=False):
    c.execute(INSERT_CONTACTO, {"t": ids["t"], "l": lead, "b": ids["b"], "estado": estado,
                                "enviado": "2026-10-18" if enviado else None,
                                "respondio": "2026-10-19" if respondio else None})


def test_un_solo_email_por_lead(rt, sembrado):
    lead = sembrado["leads"][0]
    with unidad_de_trabajo(rt, sembrado["t"]) as c:
        _contacto(c, sembrado, lead)
    with pytest.raises(DBAPIError) as exc, unidad_de_trabajo(rt, sembrado["t"]) as c:
        _contacto(c, sembrado, lead)
    assert exc.value.orig.sqlstate == UNIQUE_VIOLADO


def test_privilegios_de_app_rt(admin):
    with admin.connect() as c:
        def tiene(objeto, privilegio):
            return c.execute(text("SELECT has_table_privilege('app_rt', :o, :p)"),
                             {"o": f"public.{objeto}", "p": privilegio}).scalar()
        contactos = {p: tiene("contactos", p) for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")}
        vistas = {v: (tiene(v, "SELECT"), tiene(v, "INSERT")) for v in VISTAS}
    assert contactos == {"SELECT": True, "INSERT": True, "UPDATE": True, "DELETE": False, "TRUNCATE": False}
    assert vistas == {v: (True, False) for v in VISTAS}


@pytest.mark.parametrize("rol", ["anon", "authenticated"])
def test_privilegios_vistas(admin, rol):
    # Nombra las vistas a propósito: test_privilegios_supabase recorre pg_views y nacería verde si no existieran.
    with admin.connect() as c:
        concedidos = [(v, p) for v in [*VISTAS, "contactos"] for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
                      if c.execute(text("SELECT has_table_privilege(:r, :o, :p)"),
                                   {"r": rol, "o": f"public.{v}", "p": p}).scalar()]
    assert concedidos == []


def _tasa(rt, tenant):
    with unidad_de_trabajo(rt, tenant) as c:
        return c.execute(text("SELECT canal, contactados, respondieron, tasa FROM v_tasa_respuesta_canal")).all()


def test_tasa_respuesta_por_canal(rt, admin, sembrado, tenants):
    a, b, c_ = sembrado["leads"]
    with admin.begin() as c:
        _contacto(c, sembrado, a, "enviado", enviado=True, respondio=True)
        _contacto(c, sembrado, b, "enviado", enviado=True)
        _contacto(c, sembrado, c_)  # aprobado sin enviar: no cuenta como contactado
    filas = _tasa(rt, sembrado["t"])
    assert [(canal, n, r, float(t)) for canal, n, r, t in filas] == [("email", 2, 1, 0.5)]
    assert _tasa(rt, tenants["b"]) == []


def test_tasa_sin_contactados_es_null(rt, admin, sembrado):
    with admin.begin() as c:
        _contacto(c, sembrado, sembrado["leads"][0])
    assert _tasa(rt, sembrado["t"]) == [("email", 0, 0, None)]
