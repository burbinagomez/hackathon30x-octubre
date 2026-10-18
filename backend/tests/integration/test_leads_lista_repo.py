"""Lista de leads de la búsqueda (spec 005, enmienda 2026-10-18). Se siembra por el repo (la natural queda cifrada de
verdad) y se lee como app_rt. Datos sintéticos."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres

CS, OSM, RUES = "croma_supersociedades_co", "osm_overpass", "datos_gov_co_rues"
NOMBRE_NATURAL = "Juan Pérez Natural"
DIRECCION_NATURAL = "Calle Secreta 123"


def _empresa(nombre, fuente, id_fiscal, titular="juridica", web=None, ciudad="Bogotá", direccion=None):
    return EmpresaCruda(pais="CO", nombre=nombre, fuente=fuente, url_origen=f"https://ejemplo.invalid/{id_fiscal}",
                        as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("4711", "CIIU"), id_fiscal=id_fiscal,
                        tipo_titular=titular, ciudad=ciudad, direccion=direccion, web=web)


@pytest.fixture
def mundo(admin, tenants, rt, cifrador):
    a = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    b = RepositorioLeadsPostgres(rt, tenants["b"], cifrador)
    b1 = a.crear_busqueda(CriteriosICP("CO", {"ciiu": "4711", "departamento": "11", "ciudad": "Bogotá"}))
    b2 = a.crear_busqueda(CriteriosICP("CO", {"ciiu": "4711"}))
    ajena = b.crear_busqueda(CriteriosICP("CO", {"ciiu": "4711"}))

    def sembrar(repo, busqueda, e, lic="lic-" ):
        lead, _ = repo.obtener_o_crear_lead(e, lic + e.fuente)
        repo.agregar_lead_fuente(lead, busqueda, e, lic + e.fuente)
        return lead

    j = sembrar(a, b1, _empresa("Acme SAS", OSM, "900000001", web="https://acme.invalid"))
    sembrar(a, b1, _empresa("Acme SAS", RUES, "900000001", web="https://acme.invalid"))  # mismo lead, 2da fuente
    n = sembrar(a, b1, _empresa(NOMBRE_NATURAL, RUES, "100000002", titular="natural", direccion=DIRECCION_NATURAL))
    j2 = sembrar(a, b1, _empresa("Beta SAS", CS, "900000003"))
    sembrar(b, ajena, _empresa("Ajena SAS", OSM, "900000004"))
    return {"repo": a, "otro": b, "b1": b1, "b2": b2, "ajena": ajena, "j": j, "n": n, "j2": j2, "t": tenants}


def _por_id(pagina):
    return {i.id: i for i in pagina.items}


def test_lista_busquedas_del_tenant_con_total(mundo):
    res = {b.id: b for b in mundo["repo"].listar_busquedas()}

    assert set(res) == {mundo["b1"], mundo["b2"]}  # la de B no aparece
    assert (res[mundo["b1"]].total_leads, res[mundo["b2"]].total_leads) == (3, 0)  # el lead de 2 fuentes cuenta una vez
    b1 = res[mundo["b1"]]
    assert (b1.estado, b1.pais, b1.departamento, b1.ciudad) == ("creada", "CO", "11", "Bogotá")
    assert (res[mundo["b2"]].departamento, res[mundo["b2"]].ciudad) == (None, None)
    assert b1.creada_en.tzinfo is not None


def test_natural_sin_nombre_ni_direccion(mundo):
    p = mundo["repo"].listar_leads(mundo["b1"], 1, 25)

    n = _por_id(p)[mundo["n"]]
    assert n.tipo_titular == "natural"
    assert n.nombre is None
    assert NOMBRE_NATURAL not in repr(p) and DIRECCION_NATURAL not in repr(p)


def test_juridica_con_nombre(mundo):
    j = _por_id(mundo["repo"].listar_leads(mundo["b1"], 1, 25))[mundo["j"]]

    assert (j.nombre, j.tipo_titular, j.ciudad) == ("Acme SAS", "juridica", "Bogotá")


def test_lead_de_dos_fuentes_una_fila_con_dos_fuentes(mundo):
    p = mundo["repo"].listar_leads(mundo["b1"], 1, 25)

    assert [i.id for i in p.items].count(mundo["j"]) == 1
    j = _por_id(p)[mundo["j"]]
    assert set(j.fuentes) == {OSM, RUES}
    assert dict(zip(j.fuentes, j.licencias)) == {OSM: f"lic-{OSM}", RUES: f"lic-{RUES}"}  # licencia alineada con su fuente
    assert _por_id(p)[mundo["j2"]].fuentes == (CS,)


def test_paginacion_y_total(mundo):
    r = mundo["repo"]
    p1, p2, p3 = (r.listar_leads(mundo["b1"], n, 2) for n in (1, 2, 3))

    assert (p1.total, p1.pagina, p1.tamano) == (3, 1, 2)
    assert (len(p1.items), len(p2.items), len(p3.items)) == (2, 1, 0)
    vistos = [i.id for p in (p1, p2) for i in p.items]
    assert len(set(vistos)) == 3  # sin repetir ni perder
    assert vistos == [i.id for i in r.listar_leads(mundo["b1"], 1, 25).items]  # mismo orden estable


def test_busqueda_ajena_o_inexistente_es_none(mundo):
    r = mundo["repo"]
    assert r.listar_leads(mundo["ajena"], 1, 25) is None
    assert r.listar_leads(uuid4(), 1, 25) is None
    assert r.listar_leads(mundo["b2"], 1, 25).total == 0  # existe pero vacía: no es None


def test_tiene_web_y_contacto_sin_dato(mundo):
    p = _por_id(mundo["repo"].listar_leads(mundo["b1"], 1, 25))

    assert (p[mundo["j"]].tiene_web, p[mundo["j2"]].tiene_web, p[mundo["n"]].tiene_web) == (True, False, False)
    for i in p.values():  # no hay columna de contacto todavía: sin dato, nunca false inventado
        assert (i.tiene_telefono, i.tiene_email) == (None, None)


def test_atribuciones_solo_de_la_busqueda(mundo):
    p = mundo["repo"].listar_leads(mundo["b1"], 1, 25)

    assert [a.fuente for a in p.atribuciones] == [OSM, RUES]  # CS no tiene atribución; orden de la vista
    assert p.atribuciones[0].texto == "© OpenStreetMap contributors"
    assert p.atribuciones[0].url == "https://www.openstreetmap.org/copyright"


def test_leads_de_una_fuente_de_todas_las_busquedas_del_tenant(mundo):
    r = mundo["repo"]
    # Un lead de OSM en la segunda búsqueda: aparece en /leads?fuente=osm aunque venga de otra búsqueda.
    e = _empresa("Gamma SAS", OSM, "900000005")
    lead, _ = r.obtener_o_crear_lead(e, "lic-" + OSM)
    r.agregar_lead_fuente(lead, mundo["b2"], e, "lic-" + OSM)

    p = r.listar_leads_de_fuente(OSM, 1, 25)

    assert p.total == 2 and {i.id for i in p.items} == {mundo["j"], lead}  # no la natural, no CS, no el tenant B
    assert set(_por_id(p)[mundo["j"]].fuentes) == {OSM, RUES}  # el lead conserva todas sus fuentes
    assert [a.fuente for a in p.atribuciones] == [OSM, RUES]


def test_sin_fuente_son_todos_los_leads_del_tenant(mundo):
    p = mundo["repo"].listar_leads_de_fuente(None, 1, 2)

    assert (p.total, len(p.items)) == (3, 2)  # el lead de B no cuenta
    assert NOMBRE_NATURAL not in repr(p) and DIRECCION_NATURAL not in repr(p)
    assert mundo["otro"].listar_leads_de_fuente(None, 1, 25).total == 1


def test_fuente_sin_leads_es_pagina_vacia(mundo):
    p = mundo["repo"].listar_leads_de_fuente("croma_siem_mx", 1, 25)

    assert (p.total, p.items, p.atribuciones) == (0, (), ())
