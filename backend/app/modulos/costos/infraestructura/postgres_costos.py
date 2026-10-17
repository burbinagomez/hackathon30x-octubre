from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine

from app.modulos.costos.dominio.modelos import OperacionCosto


class PostgresCostos:
    """Libro de costos en Postgres, por tenant. Esqueleto de T024: el Verde es T025."""

    def __init__(self, engine: Engine, tenant_id: UUID):
        self._engine = engine
        self._tenant_id = tenant_id

    def registrar(self, op: OperacionCosto) -> None:
        return None

    def requests_24h(self, proveedor: str) -> int:
        return 0

    def creditos_mes(self, proveedor: str) -> Decimal:
        return Decimal(0)
