"""GET /busquedas y GET /busquedas/{id}/leads (spec 005, enmienda 2026-10-18). Sin token: lo cubre test_auth.
Se siembra por el repo con el cifrador de la propia app: si el endpoint descifrara, el nombre saldría."""
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modulos.descubrimiento.dominio.modelos import (
    Actividad,
    CriteriosICP,
    EmpresaCruda,
    ResultadoEnriquecimiento,
)
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

NOMBRE_NATURAL = "Juan Pérez Natural"
DIRECCION_NATURAL = "Calle Secreta 123"
CLAVES_DEL_ITEM = {"id", "nombre", "tipo_titular", "fuentes", "licencias", "ciudad", "tiene_telefono", "tiene_email",
                   "tiene_web"}


def _empresa(nombre, fuente, id_fiscal, titular="juridica", direccion=None, web=None):
    return EmpresaCruda(pais="CO", nombre=nombre, fuente=fuente, url_origen=f"https://ejemplo.invalid/{id_fiscal}",
                        as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("4711", "CIIU"), id_fiscal=id_fiscal,
                        tipo_titular=titular, ciudad="Bogotá", direccion=direccion, web=web)


@pytest.fixture
def datos(cliente, usuarios):
    estado = cliente.app.state
    repo = lambda t: RepositorioLeadsPostgres(estado.engine, t, estado.cifrador)  # noqa: E731
    a, b = repo(usuarios["tenant_a"]), repo(usuarios["tenant_b"])
    ba = a.crear_busqueda(CriteriosICP("CO", {"ciiu": "4711", "departamento": "11", "ciudad": "Bogotá"}))
    bb = b.crear_busqueda(CriteriosICP("CO", {"ciiu": "4711"}))
    filas = [("Acme SAS", "osm_overpass", "900000001", "juridica", None),
             (NOMBRE_NATURAL, "datos_gov_co_rues", "100000002", "natural", DIRECCION_NATURAL)]
    filas += [(f"Empresa {n} SAS", "osm_overpass", f"9000001{n:02d}", "juridica", None) for n in range(3)]
    for nombre, fuente, nit, titular, direccion in filas:
        e = _empresa(nombre, fuente, nit, titular, direccion, web="https://acme.invalid" if nit.endswith("001") else None)
        lead, _ = a.obtener_o_crear_lead(e, "lic")
        a.agregar_lead_fuente(lead, ba, e, "lic")
    e = _empresa("Ajena SAS", "osm_overpass", "900000009")
    lead, _ = b.obtener_o_crear_lead(e, "lic")
    b.agregar_lead_fuente(lead, bb, e, "lic")
    return {"api": cliente, "ba": ba, "bb": bb, "u": usuarios}


def _leads(d, quien, busqueda, **query):
    return d["api"].get(f"/busquedas/{busqueda}/leads", params=query, headers=_bearer(d["u"][quien]))


def test_404_tenant_ajeno_igual_a_inexistente(datos):
    ajeno = _leads(datos, "a", datos["bb"])
    inexistente = _leads(datos, "a", uuid4())

    assert (ajeno.status_code, inexistente.status_code) == (404, 404)
    assert ajeno.json() == inexistente.json() == {"detail": "no_encontrada"}


def test_nunca_nombre_de_natural_ni_contacto(datos):
    r = _leads(datos, "a", datos["ba"], tamano=100)

    assert r.status_code == 200
    assert NOMBRE_NATURAL not in r.text and DIRECCION_NATURAL not in r.text
    items = {i["id"]: i for i in r.json()["items"]}
    natural = next(i for i in items.values() if i["tipo_titular"] == "natural")
    assert natural["nombre"] is None
    assert all(set(i) == CLAVES_DEL_ITEM for i in items.values())  # ningún campo de más (teléfono, email, dirección)
    assert {i["nombre"] for i in items.values() if i["tipo_titular"] == "juridica"} >= {"Acme SAS"}


def test_item_trae_fuentes_licencia_y_booleanos(datos):
    r = _leads(datos, "a", datos["ba"], tamano=100).json()

    acme = next(i for i in r["items"] if i["nombre"] == "Acme SAS")
    assert (acme["fuentes"], acme["licencias"], acme["ciudad"], acme["tiene_web"]) == (
        ["osm_overpass"], ["lic"], "Bogotá", True)
    assert (acme["tiene_telefono"], acme["tiene_email"]) == (False, False)
    natural = next(i for i in r["items"] if i["tipo_titular"] == "natural")
    assert (natural["tiene_telefono"], natural["tiene_email"]) == (None, None)
    assert r["atribuciones"] == [{"fuente": "osm_overpass", "texto": "© OpenStreetMap contributors",
                                  "url": "https://www.openstreetmap.org/copyright"},
                                 {"fuente": "datos_gov_co_rues", "texto": "Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)",
                                  "url": "https://creativecommons.org/licenses/by-sa/4.0/"}]


def test_paginacion(datos):
    p1 = _leads(datos, "a", datos["ba"], pagina=1, tamano=2).json()
    p3 = _leads(datos, "a", datos["ba"], pagina=3, tamano=2).json()
    p4 = _leads(datos, "a", datos["ba"], pagina=4, tamano=2).json()

    assert (p1["total"], p1["pagina"], p1["tamano"], len(p1["items"])) == (5, 1, 2, 2)
    assert (len(p3["items"]), p4["items"]) == (1, [])
    assert p1["items"][0]["id"] not in {i["id"] for i in p3["items"]}


def test_valores_por_defecto(datos):
    r = _leads(datos, "a", datos["ba"]).json()

    assert (r["pagina"], r["tamano"], len(r["items"])) == (1, 25, 5)


@pytest.mark.parametrize("query", [{"tamano": 101}, {"tamano": 0}, {"pagina": 0}, {"pagina": -1}, {"tamano": "x"}])
def test_parametros_fuera_de_rango_son_422(datos, query):
    assert _leads(datos, "a", datos["ba"], **query).status_code == 422


def test_tamano_100_es_el_maximo(datos):
    assert _leads(datos, "a", datos["ba"], tamano=100).status_code == 200


def test_lista_de_busquedas_no_mezcla_tenants(datos):
    como_a = datos["api"].get("/busquedas", headers=_bearer(datos["u"]["a"]))
    como_b = datos["api"].get("/busquedas", headers=_bearer(datos["u"]["b"]))

    assert como_a.status_code == como_b.status_code == 200
    a, b = como_a.json()["items"], como_b.json()["items"]
    assert [i["id"] for i in a] == [str(datos["ba"])] and [i["id"] for i in b] == [str(datos["bb"])]
    assert (a[0]["total_leads"], a[0]["estado"], a[0]["pais"], a[0]["departamento"], a[0]["ciudad"]) == (
        5, "creada", "CO", "11", "Bogotá")
    assert set(a[0]) == {"id", "creada_en", "estado", "pais", "departamento", "ciudad", "total_leads"}
    json.dumps(a)  # serializable


def test_sin_logs_de_datos_de_leads(datos, caplog):
    caplog.set_level("DEBUG")
    _leads(datos, "a", datos["ba"], tamano=100)

    assert "Acme" not in caplog.text and NOMBRE_NATURAL not in caplog.text


def _de_fuente(d, quien, **query):
    return d["api"].get("/leads", params=query, headers=_bearer(d["u"][quien]))


def test_leads_de_una_fuente(datos):
    r = _de_fuente(datos, "a", fuente="osm_overpass", tamano=100)

    assert r.status_code == 200
    j = r.json()
    assert j["total"] == 4 and "Ajena SAS" not in r.text  # los 4 jurídicos de A; el de B no
    assert NOMBRE_NATURAL not in r.text and DIRECCION_NATURAL not in r.text
    assert all(set(i) == CLAVES_DEL_ITEM for i in j["items"])
    assert all(i["tipo_titular"] == "juridica" for i in j["items"])


def test_leads_sin_fuente_son_todos_los_del_tenant_y_sin_naturales_con_nombre(datos):
    r = _de_fuente(datos, "a", tamano=100)

    assert r.status_code == 200 and r.json()["total"] == 5
    assert "Ajena SAS" not in r.text and NOMBRE_NATURAL not in r.text
    assert next(i for i in r.json()["items"] if i["tipo_titular"] == "natural")["nombre"] is None
    assert _de_fuente(datos, "b").json()["total"] == 1  # B ve lo suyo


def test_fuente_desconocida_es_422(datos):
    r = _de_fuente(datos, "a", fuente="google_places")

    assert r.status_code == 422
    assert r.json() == {"errores": [{"campo": "fuente", "codigo": "desconocida"}]}


@pytest.mark.parametrize("query", [{"tamano": 101}, {"pagina": 0}])
def test_leads_de_fuente_parametros_fuera_de_rango_son_422(datos, query):
    assert _de_fuente(datos, "a", fuente="osm_overpass", **query).status_code == 422


TELEFONO = "+57 601 555 0100"
CORREO = "ventas@acme.invalid"


def _dar_contacto(datos, nombre, titular="juridica", telefono=None, email=None):
    repo = RepositorioLeadsPostgres(datos["api"].app.state.engine, datos["u"]["tenant_a"],
                                                    datos["api"].app.state.cifrador)
    ids = {i["nombre"]: i["id"] for i in _leads(datos, "a", datos["ba"], tamano=100).json()["items"] if i["nombre"]}
    repo.guardar_enriquecimiento(UUID(ids[nombre]), ResultadoEnriquecimiento(
        titular, (telefono, "sitio_web") if telefono else None, (email, "sitio_web") if email else None,
        titular == "juridica", None if titular == "juridica" else "persona_natural", None))


def test_contacto_es_booleano_y_el_valor_nunca_sale(datos):
    _dar_contacto(datos, "Acme SAS", telefono=TELEFONO, email=CORREO)

    r = _leads(datos, "a", datos["ba"], tamano=100)

    acme = next(i for i in r.json()["items"] if i["nombre"] == "Acme SAS")
    assert (acme["tiene_telefono"], acme["tiene_email"]) == (True, True)
    assert TELEFONO not in r.text and CORREO not in r.text
    assert all(set(i) == CLAVES_DEL_ITEM for i in r.json()["items"])
    assert TELEFONO not in datos["api"].get("/leads", headers=_bearer(datos["u"]["a"])).text


def test_con_contacto_filtra_en_las_dos_rutas(datos):
    _dar_contacto(datos, "Acme SAS", telefono=TELEFONO)
    _dar_contacto(datos, "Empresa 1 SAS", email=CORREO)

    por_busqueda = _leads(datos, "a", datos["ba"], con_contacto="true").json()
    todos = datos["api"].get("/leads", params={"con_contacto": "true"}, headers=_bearer(datos["u"]["a"])).json()

    for r in (por_busqueda, todos):
        assert {i["nombre"] for i in r["items"]} == {"Acme SAS", "Empresa 1 SAS"}
        assert r["total"] == 2
    assert _leads(datos, "a", datos["ba"], con_contacto="false").json()["total"] == 5
    assert _leads(datos, "a", datos["ba"]).json()["total"] == 5


def test_con_contacto_no_cruza_tenants(datos):
    _dar_contacto(datos, "Acme SAS", telefono=TELEFONO)

    como_b = datos["api"].get("/leads", params={"con_contacto": "true"}, headers=_bearer(datos["u"]["b"])).json()

    assert (como_b["total"], como_b["items"]) == (0, [])


def test_con_contacto_invalido_es_422(datos):
    assert _leads(datos, "a", datos["ba"], con_contacto="quizas").status_code == 422
