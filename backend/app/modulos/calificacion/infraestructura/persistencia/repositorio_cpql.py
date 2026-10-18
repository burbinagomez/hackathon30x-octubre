"""Solo lee `v_cpql` (la lógica vive en SQL, como `repositorio_tablero.py`). El tenant lo filtra la RLS vía security_invoker."""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo


@dataclass(frozen=True)
class FilaCPQL:
    fuente: str
    costo_lista: Decimal | None
    costo_real: Decimal | None
    calificados: int
    cpql_lista: Decimal | None
    cpql_real: Decimal | None


def leer_cpql(engine: Engine, tenant_id: UUID) -> tuple[tuple[FilaCPQL, ...], FilaCPQL | None]:
    """(filas por fuente, TOTAL). Sin datos del tenant la vista no trae TOTAL: None."""
    with unidad_de_trabajo(engine, tenant_id) as c:
        filas = [FilaCPQL(*f) for f in c.execute(text(
            "SELECT fuente, costo_lista, costo_real, calificados, cpql_lista, cpql_real FROM v_cpql ORDER BY fuente"))]
    total = next((f for f in filas if f.fuente == "TOTAL"), None)
    return tuple(f for f in filas if f.fuente != "TOTAL"), total
