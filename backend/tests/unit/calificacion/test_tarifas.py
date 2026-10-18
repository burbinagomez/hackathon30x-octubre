"""Redondeo de minutos contestados: Dapta cobra el minuto entero hacia arriba (docs.dapta.ai, Billing and credits,
aprobado por Daniel 2026-10-18). Decimal explícito: nunca `math.ceil` sobre un float."""
from decimal import Decimal

from app.modulos.calificacion.dominio.tarifas import minutos_facturables


def test_redondea_hacia_arriba_al_minuto_entero():
    assert minutos_facturables(Decimal("2.1")) == Decimal("3")


def test_minuto_exacto_no_se_redondea_de_mas():
    assert minutos_facturables(Decimal("3")) == Decimal("3")


def test_tipo_es_decimal():
    assert type(minutos_facturables(Decimal("2.1"))) is Decimal
