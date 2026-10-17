import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres

EMPRESA = EmpresaCruda(
    pais="CO", nombre="Acme SAS", fuente="croma_supersociedades_co", url_origen="https://ejemplo.invalid/acme",
    as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("4711", "CIIU"),
    id_fiscal="900123456", tipo_titular="juridica", ciudad="Bogotá",
)


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def rt():
    engine = db.crear_engine(_url("TEST_DATABASE_URL"))
    yield engine
    engine.dispose()


@pytest.fixture
def admin():
    engine = create_engine(_url("TEST_ADMIN_DATABASE_URL"))
    yield engine
    engine.dispose()


@pytest.fixture
def tenants(admin):
    """Tenants A y B, más una búsqueda y un lead de A sembrados como postgres (no pasan por el repo)."""
    ids = {"a": uuid4(), "b": uuid4(), "busqueda": uuid4(), "lead": uuid4()}
    with admin.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:a, 'A'), (:b, 'B')"), ids)
        c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:busqueda, :a, 'CO', '{}')"), ids)
        c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre) VALUES (:lead, :a, 'CO', 'sembrado')"), ids)
    yield ids
    with admin.begin() as c:
        for t in ["lead_fuentes", "cumplimiento", "leads", "busquedas"]:
            c.execute(text(f"DELETE FROM {t} WHERE tenant_id IN (:a, :b)"), ids)
        c.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), ids)


def _contar(admin, sql, **params):
    with admin.connect() as c:
        return c.execute(text(sql), params).scalar()


def test_unico_por_tenant_pais_id_fiscal(rt, admin, tenants):
    repo = RepositorioLeadsPostgres(rt, tenants["a"])
    primero = repo.obtener_o_crear_lead(EMPRESA, "licencia-x")
    segundo = repo.obtener_o_crear_lead(EMPRESA, "licencia-x")
    assert segundo == (primero[0], False)
    assert _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :t AND id_fiscal = :f",
                   t=tenants["a"], f=EMPRESA.id_fiscal) == 1


def test_mismo_id_fiscal_en_otro_tenant_es_otro_lead(rt, admin, tenants):
    lead_a, _ = RepositorioLeadsPostgres(rt, tenants["a"]).obtener_o_crear_lead(EMPRESA, "licencia-x")
    lead_b, nuevo = RepositorioLeadsPostgres(rt, tenants["b"]).obtener_o_crear_lead(EMPRESA, "licencia-x")
    assert nuevo is True and lead_b != lead_a
    assert _contar(admin, "SELECT tenant_id FROM leads WHERE id = :id", id=lead_b) == tenants["b"]


def test_unico_lead_fuente_busqueda(rt, admin, tenants):
    repo = RepositorioLeadsPostgres(rt, tenants["a"])
    repo.agregar_lead_fuente(tenants["lead"], tenants["busqueda"], EMPRESA, "licencia-x")
    repo.agregar_lead_fuente(tenants["lead"], tenants["busqueda"], EMPRESA, "licencia-x")  # ON CONFLICT DO NOTHING
    assert _contar(admin, "SELECT count(*) FROM lead_fuentes WHERE lead_id = :l AND busqueda_id = :b AND fuente = :f",
                   l=tenants["lead"], b=tenants["busqueda"], f=EMPRESA.fuente) == 1


def test_lead_persistido_conserva_tipo_titular(rt, admin, tenants):
    lead_id, _ = RepositorioLeadsPostgres(rt, tenants["a"]).obtener_o_crear_lead(EMPRESA, "licencia-x")
    with admin.connect() as c:
        fila = c.execute(text("SELECT tipo_titular, pais, id_fiscal, nombre FROM leads WHERE id = :id"),
                         {"id": lead_id}).one_or_none()
        cumplimiento = c.execute(text("SELECT fuente, licencia, url_origen FROM cumplimiento WHERE lead_id = :id"),
                                 {"id": lead_id}).one_or_none()
    assert fila == ("juridica", "CO", "900123456", "Acme SAS")
    assert cumplimiento == (EMPRESA.fuente, "licencia-x", EMPRESA.url_origen)


def test_lead_nuevo_y_cumplimiento_en_una_transaccion(rt, admin, tenants):
    # licencia NULL: el INSERT del lead pasa y el de cumplimiento viola NOT NULL.
    with pytest.raises(IntegrityError):
        RepositorioLeadsPostgres(rt, tenants["a"]).obtener_o_crear_lead(EMPRESA, None)
    assert _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :t AND id_fiscal = :f",
                   t=tenants["a"], f=EMPRESA.id_fiscal) == 0


def test_crear_busqueda_se_confirma_antes(rt, admin, tenants):
    busqueda_id = RepositorioLeadsPostgres(rt, tenants["a"]).crear_busqueda(
        CriteriosICP(pais="CO", filtros={"ciiu": ("4711",)}))
    # otra conexión, antes de que nadie llame a un adaptador
    with admin.connect() as c:
        fila = c.execute(text("SELECT tenant_id, pais, estado FROM busquedas WHERE id = :id"),
                         {"id": busqueda_id}).one_or_none()
    assert fila == (tenants["a"], "CO", "creada")
