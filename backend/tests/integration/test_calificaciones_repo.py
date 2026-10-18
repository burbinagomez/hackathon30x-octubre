"""Integración de `PostgresCalificaciones` (T010/T011, revisión de security): juridica + cumplimiento antes de
importar, cruce de tenant no distinguible por fuera de RLS, y atomicidad calificación+costo en una transacción."""
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.modulos.calificacion.dominio.modelos import ResultadoCalificacion
from app.modulos.calificacion.infraestructura.persistencia.postgres_calificaciones import PostgresCalificaciones
from app.modulos.costos.dominio.modelos import OperacionCosto

FECHA = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def tenant(admin):
    a = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:a, 'A')"), {"a": a})
    yield a
    with admin.begin() as c:
        c.execute(text("DELETE FROM calificaciones WHERE tenant_id = :a"), {"a": a})
        c.execute(text("DELETE FROM costos WHERE tenant_id = :a"), {"a": a})
        c.execute(text("DELETE FROM cumplimiento WHERE tenant_id = :a"), {"a": a})
        c.execute(text("DELETE FROM leads WHERE tenant_id = :a"), {"a": a})
        c.execute(text("DELETE FROM tenants WHERE id = :a"), {"a": a})


def _lead(admin, tenant_id, tipo_titular="juridica", con_cumplimiento=True):
    lead_id = uuid4()
    with admin.begin() as c:
        if tipo_titular == "juridica":
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) VALUES "
                           "(:id, :t, 'CO', 'Empresa', :tt)"), {"id": lead_id, "t": tenant_id, "tt": tipo_titular})
        else:
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular, nombre_cifrado) VALUES "
                           "(:id, :t, 'CO', NULL, :tt, :nc)"),
                      {"id": lead_id, "t": tenant_id, "tt": tipo_titular, "nc": b"0" * 29})
        if con_cumplimiento:
            c.execute(text("INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
                           "VALUES (:t, :id, 'osm_overpass', 'ODbL', 'u', now())"), {"id": lead_id, "t": tenant_id})
    return lead_id


def _costo(resultado):
    return OperacionCosto(tipo="dapta_llamada", unidades=Decimal("2"), costo_unitario=Decimal("0.333"), moneda="USD",
                          proveedor="dapta", fuente=None, canal=None, lead_id=resultado.lead_id, lote_id=None,
                          gratis=False, ts=resultado.fecha)


def test_lead_natural_es_no_cumple(rt, admin, tenant):
    lead_id = _lead(admin, tenant, tipo_titular="natural")
    resultado = ResultadoCalificacion(lead_id, True, FECHA, Decimal("2"))

    estado = PostgresCalificaciones(rt, tenant).guardar(resultado, _costo(resultado))

    assert estado == "no_cumple"
    with admin.connect() as c:
        assert c.execute(text("SELECT count(*) FROM calificaciones WHERE tenant_id = :t"), {"t": tenant}).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM costos WHERE tenant_id = :t"), {"t": tenant}).scalar() == 0


def test_lead_sin_cumplimiento_es_no_cumple(rt, admin, tenant):
    lead_id = _lead(admin, tenant, con_cumplimiento=False)
    resultado = ResultadoCalificacion(lead_id, True, FECHA, Decimal("2"))

    estado = PostgresCalificaciones(rt, tenant).guardar(resultado, _costo(resultado))

    assert estado == "no_cumple"
    with admin.connect() as c:
        assert c.execute(text("SELECT count(*) FROM calificaciones WHERE tenant_id = :t"), {"t": tenant}).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM costos WHERE tenant_id = :t"), {"t": tenant}).scalar() == 0


def test_lead_de_otro_tenant_es_ref_desconocida(rt, admin, tenant):
    otro = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:o, 'Otro')"), {"o": otro})
    lead_de_otro = _lead(admin, otro)  # juridica + cumplimiento, pero de otro tenant
    resultado = ResultadoCalificacion(lead_de_otro, True, FECHA, Decimal("2"))

    try:
        estado = PostgresCalificaciones(rt, tenant).guardar(resultado, _costo(resultado))

        assert estado == "ref_desconocida"
        with admin.connect() as c:
            assert c.execute(text("SELECT count(*) FROM calificaciones WHERE lead_id = :l"),
                             {"l": lead_de_otro}).scalar() == 0
    finally:
        with admin.begin() as c:
            c.execute(text("DELETE FROM cumplimiento WHERE tenant_id = :o"), {"o": otro})
            c.execute(text("DELETE FROM leads WHERE tenant_id = :o"), {"o": otro})
            c.execute(text("DELETE FROM tenants WHERE id = :o"), {"o": otro})


def test_importada_escribe_calificacion_y_costo(rt, admin, tenant):
    lead_id = _lead(admin, tenant)
    resultado = ResultadoCalificacion(lead_id, True, FECHA, Decimal("2"))

    estado = PostgresCalificaciones(rt, tenant).guardar(resultado, _costo(resultado))

    assert estado == "importada"
    with admin.connect() as c:
        calif = c.execute(text("SELECT calificado, calificado_en, minutos FROM calificaciones "
                               "WHERE tenant_id = :t AND lead_id = :l"), {"t": tenant, "l": lead_id}).one()
        costo = c.execute(text("SELECT tipo, unidades, costo_unitario, moneda, proveedor, fuente, canal, lead_id, "
                               "lote_id, gratis, ts FROM costos WHERE tenant_id = :t"), {"t": tenant}).one()
    assert calif == (True, FECHA, Decimal("2"))
    assert costo == ("dapta_llamada", Decimal("2"), Decimal("0.333"), "USD", "dapta", None, None, lead_id,
                     None, False, FECHA)


def test_duplicada_mismo_resultado_no_escribe_costo_de_nuevo(rt, admin, tenant):
    lead_id = _lead(admin, tenant)
    resultado = ResultadoCalificacion(lead_id, True, FECHA, Decimal("2"))
    repo = PostgresCalificaciones(rt, tenant)
    repo.guardar(resultado, _costo(resultado))

    estado = repo.guardar(resultado, _costo(resultado))

    assert estado == "duplicada"
    with admin.connect() as c:
        assert c.execute(text("SELECT count(*) FROM costos WHERE tenant_id = :t"), {"t": tenant}).scalar() == 1


def test_conflicto_resultado_distinto_no_cambia_nada(rt, admin, tenant):
    lead_id = _lead(admin, tenant)
    primero = ResultadoCalificacion(lead_id, True, FECHA, Decimal("2"))
    repo = PostgresCalificaciones(rt, tenant)
    repo.guardar(primero, _costo(primero))

    distinto = ResultadoCalificacion(lead_id, False, FECHA, Decimal("5"))
    estado = repo.guardar(distinto, _costo(distinto))

    assert estado == "conflicto"
    with admin.connect() as c:
        calif = c.execute(text("SELECT calificado, minutos FROM calificaciones WHERE tenant_id = :t AND lead_id = :l"),
                          {"t": tenant, "l": lead_id}).one()
        n_costos = c.execute(text("SELECT count(*) FROM costos WHERE tenant_id = :t"), {"t": tenant}).scalar()
    assert calif == (True, Decimal("2"))  # el primer resultado no se tocó
    assert n_costos == 1  # no se agregó un segundo costo por el conflicto


def test_calificacion_y_costo_en_la_misma_transaccion(rt, admin, tenant):
    """Si el INSERT de costos falla, la calificación tampoco queda: lo prueba una `OperacionCosto` con un
    `tipo` que viola el CHECK de `costos` (la fila nunca es válida), y confirma que ninguna de las dos quedó."""
    lead_id = _lead(admin, tenant)
    resultado = ResultadoCalificacion(lead_id, True, FECHA, Decimal("2"))
    costo_invalido = OperacionCosto(tipo="tipo_invalido_no_existe", unidades=Decimal("2"), costo_unitario=Decimal("0.333"),
                                    moneda="USD", proveedor="dapta", fuente=None, canal=None, lead_id=lead_id,
                                    lote_id=None, gratis=False, ts=resultado.fecha)

    with pytest.raises(IntegrityError):
        PostgresCalificaciones(rt, tenant).guardar(resultado, costo_invalido)

    with admin.connect() as c:
        assert c.execute(text("SELECT count(*) FROM calificaciones WHERE tenant_id = :t"), {"t": tenant}).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM costos WHERE tenant_id = :t"), {"t": tenant}).scalar() == 0


def test_mismo_calificado_con_otros_minutos_es_conflicto(rt, admin, tenant):
    """Duplicada = mismo (calificado, minutos). Otros minutos cambian el costo: es conflicto, no un no-op."""
    lead_id = _lead(admin, tenant)
    primero = ResultadoCalificacion(lead_id, True, FECHA, Decimal("2"))
    repo = PostgresCalificaciones(rt, tenant)
    repo.guardar(primero, _costo(primero))

    otros_minutos = ResultadoCalificacion(lead_id, True, FECHA, Decimal("5"))
    estado = repo.guardar(otros_minutos, _costo(otros_minutos))

    assert estado == "conflicto"
