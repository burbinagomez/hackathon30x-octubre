"""Spec 015, integración: el savepoint por fuente contra Postgres de verdad (rol app_rt, RLS)."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBorrador
from app.modulos.descubrimiento.dominio.errores import ErrorPersistencia
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda, MetaFuente
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from tests.falsos import FabricaFalsa, RegistroCostosFalso

AS_OF = datetime(2026, 10, 1, tzinfo=UTC)
A, B = "fuente_a", "fuente_b"


def _meta(clave):
    return MetaFuente(clave=clave, proveedor=clave, paises=frozenset({"CO"}), filtros=frozenset({"ciiu", "departamento"}),
                      trae=frozenset({"nombre"}), tipo="live", licencia=f"lic_{clave}", costo_maximo_llamada=Decimal(0))


def _empresa(fuente, nit, titular="juridica"):
    return EmpresaCruda(pais="CO", nombre=f"EMPRESA {nit} SAS", fuente=fuente, url_origen=f"https://{fuente}.test/{nit}",
                        as_of=AS_OF, actividad=Actividad("1081", "CIIU"), id_fiscal=nit, tipo_titular=titular)


@pytest.fixture
def tenant(admin):
    t = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:t, 'A')"), {"t": t})
    yield t
    with admin.begin() as c:
        for tabla in ("lead_fuentes", "cumplimiento", "leads", "costos", "busquedas"):
            c.execute(text(f"DELETE FROM {tabla} WHERE tenant_id = :t"), {"t": t})
        c.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": t})


def test_falla_al_persistir_una_fuente_deshace_solo_esa(rt, admin, tenant, cifrador):
    repo = RepositorioLeadsPostgres(rt, tenant, cifrador)
    costos = RegistroCostosFalso()
    # A: la primera empresa es válida y la segunda viola el CHECK de tipo_titular (la base la rechaza).
    empresas = {A: (_empresa(A, "900000001"), _empresa(A, "900000002", titular="invalido")),
                B: (_empresa(B, "900000003"),)}
    fabrica = FabricaFalsa(costos, {A: _meta(A), B: _meta(B)}, empresas)
    icp = CriteriosICP("CO", {"ciiu": "1081", "departamento": "73"})
    busqueda_id = repo.crear_borrador(icp, "email", Decimal("5"), None)

    r = EjecutarBorrador(repo, fabrica, {}, costos).ejecutar(busqueda_id)

    assert {k: (v.estado, v.encontrados) for k, v in r.por_fuente.items()} == {A: ("no_disponible", 0), B: ("con_resultados", 1)}
    assert isinstance(r.errores[A], ErrorPersistencia)
    with admin.connect() as c:
        leads = c.execute(text("SELECT id_fiscal FROM leads WHERE tenant_id = :t"), {"t": tenant}).scalars().all()
        fuentes = c.execute(text("SELECT fuente FROM lead_fuentes WHERE tenant_id = :t"), {"t": tenant}).scalars().all()
        cumple = c.execute(text("SELECT fuente FROM cumplimiento WHERE tenant_id = :t"), {"t": tenant}).scalars().all()
        estado = c.execute(text("SELECT estado FROM busquedas WHERE id = :b"), {"b": busqueda_id}).scalar_one()
    assert leads == ["900000003"]  # ni el lead válido de A queda: se deshizo toda la fuente
    assert fuentes == [B] and cumple == [B]
    assert estado == "completada"
