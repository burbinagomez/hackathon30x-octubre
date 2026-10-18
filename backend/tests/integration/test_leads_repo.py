from dataclasses import replace
from decimal import Decimal
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modulos.descubrimiento.dominio.errores import ErrorPersistencia
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres

EMPRESA = EmpresaCruda(
    pais="CO", nombre="Acme SAS", fuente="croma_supersociedades_co", url_origen="https://ejemplo.invalid/acme",
    as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("4711", "CIIU"),
    id_fiscal="900123456", tipo_titular="juridica", ciudad="Bogotá",
)


@pytest.fixture
def tenants(admin):
    """Tenants A y B, más una búsqueda y un lead de A sembrados como postgres (no pasan por el repo)."""
    ids = {"a": uuid4(), "b": uuid4(), "busqueda": uuid4(), "lead": uuid4()}
    with admin.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:a, 'A'), (:b, 'B')"), ids)
        c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:busqueda, :a, 'CO', '{}')"), ids)
        c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) VALUES (:lead, :a, 'CO', 'sembrado', 'juridica')"), ids)
    yield ids
    with admin.begin() as c:
        for t in ["lead_fuentes", "cumplimiento", "leads", "busquedas"]:
            c.execute(text(f"DELETE FROM {t} WHERE tenant_id IN (:a, :b)"), ids)
        c.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), ids)


def _contar(admin, sql, **params):
    with admin.connect() as c:
        return c.execute(text(sql), params).scalar()


def test_unico_por_tenant_pais_id_fiscal(rt, admin, tenants, cifrador):
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    primero = repo.obtener_o_crear_lead(EMPRESA, "licencia-x")
    segundo = repo.obtener_o_crear_lead(EMPRESA, "licencia-x")
    assert segundo == (primero[0], False)
    assert _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :t AND id_fiscal = :f",
                   t=tenants["a"], f=EMPRESA.id_fiscal) == 1


def test_mismo_id_fiscal_en_otro_tenant_es_otro_lead(rt, admin, tenants, cifrador):
    lead_a, _ = RepositorioLeadsPostgres(rt, tenants["a"], cifrador).obtener_o_crear_lead(EMPRESA, "licencia-x")
    lead_b, nuevo = RepositorioLeadsPostgres(rt, tenants["b"], cifrador).obtener_o_crear_lead(EMPRESA, "licencia-x")
    assert nuevo is True and lead_b != lead_a
    assert _contar(admin, "SELECT tenant_id FROM leads WHERE id = :id", id=lead_b) == tenants["b"]


def test_unico_lead_fuente_busqueda(rt, admin, tenants, cifrador):
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    repo.agregar_lead_fuente(tenants["lead"], tenants["busqueda"], EMPRESA, "licencia-x")
    repo.agregar_lead_fuente(tenants["lead"], tenants["busqueda"], EMPRESA, "licencia-x")  # ON CONFLICT DO NOTHING
    assert _contar(admin, "SELECT count(*) FROM lead_fuentes WHERE lead_id = :l AND busqueda_id = :b AND fuente = :f",
                   l=tenants["lead"], b=tenants["busqueda"], f=EMPRESA.fuente) == 1


@pytest.mark.parametrize("tipo_titular", ["juridica", "desconocido"])
def test_lead_persistido_conserva_tipo_titular(rt, admin, tenants, cifrador, tipo_titular):
    empresa = replace(EMPRESA, tipo_titular=tipo_titular)
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    lead_id, _ = repo.obtener_o_crear_lead(empresa, "licencia-x")
    with admin.connect() as c:
        fila = c.execute(text("SELECT tipo_titular, pais, id_fiscal FROM leads WHERE id = :id"),
                         {"id": lead_id}).one_or_none()
        cumplimiento = c.execute(text("SELECT fuente, licencia, url_origen, as_of FROM cumplimiento WHERE lead_id = :id"),
                                 {"id": lead_id}).one_or_none()
    assert fila == (tipo_titular, "CO", "900123456")
    assert repo.obtener_lead(lead_id).nombre == "Acme SAS"  # el nombre solo se lee por el repositorio
    assert cumplimiento == (EMPRESA.fuente, "licencia-x", EMPRESA.url_origen, EMPRESA.as_of)


def test_lead_nuevo_y_cumplimiento_en_una_transaccion(rt, admin, tenants, cifrador):
    # licencia NULL: el INSERT del lead pasa y el de cumplimiento viola NOT NULL.
    with pytest.raises(ErrorPersistencia):
        RepositorioLeadsPostgres(rt, tenants["a"], cifrador).obtener_o_crear_lead(EMPRESA, None)
    assert _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :t AND id_fiscal = :f",
                   t=tenants["a"], f=EMPRESA.id_fiscal) == 0


def test_crear_busqueda_se_confirma_antes(rt, admin, tenants, cifrador):
    busqueda_id = RepositorioLeadsPostgres(rt, tenants["a"], cifrador).crear_busqueda(
        CriteriosICP(pais="CO", filtros={"ciiu": ("4711",)}))
    # otra conexión, antes de que nadie llame a un adaptador
    with admin.connect() as c:
        fila = c.execute(text("SELECT tenant_id, pais, estado FROM busquedas WHERE id = :id"),
                         {"id": busqueda_id}).one_or_none()
    assert fila == (tenants["a"], "CO", "creada")


def test_cerrar_busqueda_guarda_estado(rt, admin, tenants, cifrador):
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    busqueda_id = repo.crear_busqueda(CriteriosICP(pais="CO", filtros={}))
    repo.cerrar_busqueda(busqueda_id, "con_errores")
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "con_errores"


# --- Borradores (T025, P2) ---

CRITERIOS = CriteriosICP(pais="CO", filtros={"ciiu": "4711", "departamento": ("Cundinamarca", "Antioquia")})


def test_borrador_se_guarda_y_se_lee_con_sus_criterios_congelados(rt, admin, tenants, cifrador):
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)

    busqueda_id = repo.crear_borrador(CRITERIOS, "email", Decimal("5.25"), "Hola")

    b = repo.obtener_borrador(busqueda_id)
    assert b is not None
    assert b.id == busqueda_id
    assert b.criterios == CRITERIOS  # la tupla vuelve como tupla, no como lista
    assert (b.canal_preferido, b.mensaje_base) == ("email", "Hola")
    assert b.tope_gasto_usd == Decimal("5.25") and type(b.tope_gasto_usd) is Decimal
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "borrador"


def test_borrador_de_a_no_se_ve_ni_se_ejecuta_desde_b(rt, admin, tenants, cifrador):
    busqueda_id = RepositorioLeadsPostgres(rt, tenants["a"], cifrador).crear_borrador(CRITERIOS, None, Decimal("1"), None)
    repo_b = RepositorioLeadsPostgres(rt, tenants["b"], cifrador)

    assert repo_b.obtener_borrador(busqueda_id) is None
    assert repo_b.pasar_a_ejecutando(busqueda_id) is False
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "borrador"


def test_pasar_a_ejecutando_funciona_una_sola_vez(rt, admin, tenants, cifrador):
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    busqueda_id = repo.crear_borrador(CRITERIOS, None, Decimal("1"), None)

    assert repo.pasar_a_ejecutando(busqueda_id) is True
    assert repo.pasar_a_ejecutando(busqueda_id) is False
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "ejecutando"
    assert repo.obtener_borrador(busqueda_id) is None  # ya no es borrador


def test_obtener_borrador_no_devuelve_una_busqueda_que_no_es_borrador(rt, tenants, cifrador):
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    assert repo.obtener_borrador(tenants["busqueda"]) is None  # sembrada en `creada`
    assert repo.pasar_a_ejecutando(tenants["busqueda"]) is False
