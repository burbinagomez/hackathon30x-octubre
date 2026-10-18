from dataclasses import asdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo
from app.modulos.costos.dominio.modelos import OperacionCosto

_INSERT = text(
    "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, canal, lead_id, "
    "lote_id, gratis, ts) VALUES (:t, :tipo, :unidades, :costo_unitario, :moneda, :proveedor, :fuente, :canal, "
    ":lead_id, :lote_id, :gratis, COALESCE(CAST(:ts AS timestamptz), now()))"
)


class PostgresCostos:
    """Libro de costos en Postgres, por tenant (RLS). Cada `registrar` en su propia transacción."""

    def __init__(self, engine: Engine, tenant_id: UUID):
        self._engine = engine
        self._tenant_id = tenant_id

    def registrar(self, op: OperacionCosto) -> None:
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            c.execute(_INSERT, {"t": self._tenant_id, **asdict(op)})

    def requests_24h(self, proveedor: str) -> int:
        # COUNT y no SUM: un 502 (unidades=0) también gasta request.
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            return c.execute(
                text("SELECT count(*) FROM costos WHERE proveedor = :p AND ts > now() - interval '24 hours'"),
                {"p": proveedor},
            ).scalar_one()

    def creditos_mes(self, proveedor: str) -> Decimal:
        # Mes calendario UTC, sin importar la zona de la sesión.
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            return c.execute(
                text("SELECT COALESCE(sum(unidades), 0) FROM costos WHERE proveedor = :p "
                     "AND ts >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"),
                {"p": proveedor},
            ).scalar_one()

    def gasto_busqueda(self, busqueda_id: UUID) -> Decimal:
        # A valor de lista, gratis incluido (el tier gratis se acaba en medio de una búsqueda). COALESCE: sin filas, 0 y no NULL.
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            return c.execute(
                text("SELECT COALESCE(sum(unidades * costo_unitario), 0) FROM costos WHERE lote_id = :lote"),
                {"lote": busqueda_id},
            ).scalar_one()
