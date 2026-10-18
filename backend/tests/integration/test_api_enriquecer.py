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


def test_enriquece_y_devuelve_solo_conteos(cliente, admin, usuarios):
    cliente.app.state.transporte_http = httpx.MockTransport(_sitio)
    cliente.app.state.resolver_dns = lambda host: ["93.184.216.34"]  # público: pasa la guarda SSRF
    busqueda, lead_id = _busqueda_con_lead(cliente, admin, usuarios["tenant_a"])

    r = cliente.post(f"/busquedas/{busqueda}/enriquecer", headers=_bearer(usuarios["a"]))

    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == {"procesados", "contactables", "clasificados", "sin_clasificar", "cortado", "pendientes"}
    assert (cuerpo["procesados"], cuerpo["pendientes"]) == (1, 0)
    assert "andinos" not in r.text and "555" not in r.text  # nunca el contacto en la respuesta
    with admin.connect() as c:
        fila = c.execute(text("SELECT enriquecido_en, telefono_cifrado FROM leads WHERE id = :id"), {"id": lead_id}).one()
    assert fila.enriquecido_en is not None and fila.telefono_cifrado is not None
