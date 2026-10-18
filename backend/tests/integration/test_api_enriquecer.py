"""POST /busquedas/{id}/enriquecer: el mismo caso de uso que la CLI, por tandas y con sesión. Sitio web y DNS falsos."""
from uuid import uuid4

import httpx
from sqlalchemy import text

from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

HTML = "<html><body>Escríbanos a ventas@andinos.invalid · Tel +57 602 555 0101</body></html>"


def _sitio(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})


def _busqueda_con_lead(cliente, admin, tenant_id, web="andinos.invalid"):
    from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda
    from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
    from datetime import UTC, datetime

    repo = RepositorioLeadsPostgres(cliente.app.state.engine, tenant_id, cliente.app.state.cifrador)
    busqueda = repo.crear_busqueda(CriteriosICP("CO", {}))
    e = EmpresaCruda(pais="CO", nombre="Andinos SAS", fuente="osm_overpass", url_origen="https://ejemplo.invalid/o",
                     as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("5229", "CIIU"),
                     tipo_titular="juridica", ciudad="Cali", direccion="Calle 1", web=web)
    lead_id, _ = repo.obtener_o_crear_lead(e, "odbl")
    repo.agregar_lead_fuente(lead_id, busqueda, e, "odbl")
    return busqueda, lead_id


def test_sin_sesion_es_401(cliente):
    assert cliente.post(f"/busquedas/{uuid4()}/enriquecer").status_code == 401


def test_busqueda_de_otro_tenant_es_404(cliente, admin, usuarios):
    busqueda, _ = _busqueda_con_lead(cliente, admin, usuarios["tenant_b"])
    r = cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))
    assert (r.status_code, r.json()) == (404, {"detail": "no_encontrada"})


def _con_sitio_falso(cliente):
    cliente.app.state.transporte_http = httpx.MockTransport(_sitio)
    cliente.app.state.resolver_dns = lambda host: ["93.184.216.34"]  # público: pasa la guarda SSRF


def test_la_tanda_enriquece_y_devuelve_solo_conteos(cliente, admin, usuarios):
    from app.api.enriquecimiento import tanda
    _con_sitio_falso(cliente)
    busqueda, lead_id = _busqueda_con_lead(cliente, admin, usuarios["tenant_a"])

    r = tanda(cliente.app.state, usuarios["tenant_a"], busqueda)

    assert (r.procesados, r.pendientes) == (1, 0)
    with admin.connect() as c:
        fila = c.execute(text("SELECT enriquecido_en, telefono_cifrado FROM leads WHERE id = :id"), {"id": lead_id}).one()
        costos = c.execute(text("SELECT count(*) FROM costos WHERE tenant_id = :t"), {"t": usuarios["tenant_a"]}).scalar()
    assert fila.enriquecido_en is not None and fila.telefono_cifrado is not None
    assert costos > 0  # cada operación de salida deja su fila


def test_post_arranca_en_segundo_plano_y_responde_202_sin_contacto(cliente, admin, usuarios):
    lanzados = []
    cliente.app.state.lanzador_enriquecimiento = lanzados.append  # el trabajo no corre: el endpoint no espera nada
    busqueda, _ = _busqueda_con_lead(cliente, admin, usuarios["tenant_a"])

    r = cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))

    assert r.status_code == 202
    assert len(lanzados) == 1
    cuerpo = r.json()
    assert (cuerpo["en_curso"], cuerpo["pendientes"], cuerpo["total"], cuerpo["error"]) == (True, 1, 1, None)
    assert "andinos" not in r.text and "555" not in r.text


def test_post_dos_veces_no_duplica_el_proceso(cliente, admin, usuarios):
    lanzados = []
    cliente.app.state.lanzador_enriquecimiento = lanzados.append
    busqueda, _ = _busqueda_con_lead(cliente, admin, usuarios["tenant_a"])

    r1 = cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))
    r2 = cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))

    assert (r1.status_code, r2.status_code) == (202, 202)
    assert len(lanzados) == 1 and r2.json()["en_curso"] is True


def test_el_proceso_completo_enriquece_y_el_get_da_el_progreso(cliente, admin, usuarios):
    _con_sitio_falso(cliente)
    cliente.app.state.lanzador_enriquecimiento = lambda trabajo: trabajo()  # síncrono: determinista
    busqueda, lead_id = _busqueda_con_lead(cliente, admin, usuarios["tenant_a"])

    cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))
    r = cliente.get(f"/busquedas/{busqueda}/enriquecimiento", headers=_bearer(usuarios["a"]))

    assert r.status_code == 200
    assert r.json() == {"en_curso": False, "procesados": 1, "contactables": 1, "pendientes": 0, "total": 1, "error": None}
    assert "andinos" not in r.text and "555" not in r.text


def test_get_sin_nada_en_memoria_calcula_desde_la_base(cliente, admin, usuarios):
    busqueda, _ = _busqueda_con_lead(cliente, admin, usuarios["tenant_a"])

    r = cliente.get(f"/busquedas/{busqueda}/enriquecimiento", headers=_bearer(usuarios["a"]))

    assert r.json() == {"en_curso": False, "procesados": 0, "contactables": 0, "pendientes": 1, "total": 1, "error": None}


def test_get_no_cruza_tenants(cliente, admin, usuarios):
    busqueda, _ = _busqueda_con_lead(cliente, admin, usuarios["tenant_b"])
    r = cliente.get(f"/busquedas/{busqueda}/enriquecimiento", headers=_bearer(usuarios["a"]))
    assert (r.status_code, r.json()) == (404, {"detail": "no_encontrada"})
    assert cliente.get(f"/busquedas/{uuid4()}/enriquecimiento").status_code == 401


def test_una_tanda_que_falla_queda_en_el_estado_con_solo_el_codigo(cliente, admin, usuarios):
    def rota(estado, tenant_id, busqueda_id):
        raise RuntimeError("secreto andinos@x.invalid")

    cliente.app.state.tanda_enriquecimiento = rota
    cliente.app.state.lanzador_enriquecimiento = lambda trabajo: trabajo()
    busqueda, _ = _busqueda_con_lead(cliente, admin, usuarios["tenant_a"])

    cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))
    r = cliente.get(f"/busquedas/{busqueda}/enriquecimiento", headers=_bearer(usuarios["a"]))

    assert (r.json()["en_curso"], r.json()["error"], r.json()["pendientes"]) == (False, "error_tanda", 1)
    assert "andinos" not in r.text


def test_repite_tandas_hasta_que_no_quedan_pendientes(cliente, admin, usuarios):
    from app.modulos.enriquecimiento.aplicacion.enriquecer_lead import ResumenEnriquecimiento
    pendientes = iter([2, 1, 0])
    cliente.app.state.tanda_enriquecimiento = lambda e, t, b: ResumenEnriquecimiento(1, 1, 0, 1, False, next(pendientes))
    cliente.app.state.lanzador_enriquecimiento = lambda trabajo: trabajo()
    busqueda, _ = _busqueda_con_lead(cliente, admin, usuarios["tenant_a"])

    cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))

    assert next(pendientes, "agotado") == "agotado"  # las tres tandas corrieron
