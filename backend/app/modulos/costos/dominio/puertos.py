from decimal import Decimal
from typing import Protocol

from app.modulos.costos.dominio.modelos import OperacionCosto


class RegistroCostos(Protocol):
    def registrar(self, op: OperacionCosto) -> None:
        """Transacción propia: el gasto queda aunque falle lo que viene después."""
        ...

    def requests_24h(self, proveedor: str) -> int: ...

    def creditos_mes(self, proveedor: str) -> Decimal: ...
