from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.modulos.costos.dominio.modelos import OperacionCosto


class RegistroCostos(Protocol):
    def registrar(self, op: OperacionCosto) -> None:
        """Transacción propia: el gasto queda aunque falle lo que viene después."""
        ...

    def requests_24h(self, proveedor: str) -> int: ...

    def creditos_mes(self, proveedor: str) -> Decimal: ...

    def gasto_busqueda(self, busqueda_id: UUID) -> Decimal:
        """Σ unidades × costo_unitario de las filas del lote (= búsqueda), a valor de lista y gratis incluido. Sin filas: 0."""
        ...
