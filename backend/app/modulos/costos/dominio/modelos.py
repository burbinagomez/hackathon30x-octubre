from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class OperacionCosto:  # skill libro-costos + gratis
    tipo: str
    unidades: Decimal
    costo_unitario: Decimal
    moneda: str
    proveedor: str
    fuente: str | None
    canal: str | None
    lead_id: UUID | None
    lote_id: UUID | None
    gratis: bool
    ts: datetime | None = None  # None = now() de la base
