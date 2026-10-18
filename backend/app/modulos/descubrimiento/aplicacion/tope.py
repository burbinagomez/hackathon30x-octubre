"""Tope de gasto de una búsqueda (spec 005, "Tope de gasto"): todo a valor de lista, en Decimal.

El adaptador declara el peor caso de UNA llamada (`MetaFuente.costo_maximo_llamada`); el tope lo aplica el caso de uso,
nunca el adaptador, que no lo conoce.
"""
from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.dominio.modelos import MetaFuente


def costo_maximo(costos: RegistroCostos, busqueda_id: UUID, metas: Iterable[MetaFuente]) -> Decimal:
    """Lo ya gastado en el lote + el peor caso de cada fuente que se va a llamar."""
    return costos.gasto_busqueda(busqueda_id) + sum((m.costo_maximo_llamada for m in metas), Decimal(0))


def cabe_otra_llamada(costos: RegistroCostos, busqueda_id: UUID, meta: MetaFuente, tope: Decimal) -> bool:
    """`gasto_busqueda + costo_maximo_llamada <= tope`, medido con el libro AHORA (el gasto puede haber crecido)."""
    return costos.gasto_busqueda(busqueda_id) + meta.costo_maximo_llamada <= tope
