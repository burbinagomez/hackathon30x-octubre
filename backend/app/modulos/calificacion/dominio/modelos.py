from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class ResultadoCalificacion:
    """Una fila válida del CSV de Dapta (plan.md): el lead, si contestó que sí, y cuánto duró la llamada."""
    lead_id: UUID
    calificado: bool
    fecha: datetime
    minutos: Decimal


@dataclass(frozen=True)
class FilaRechazada:
    """`fila` es el número de línea (1-based, sin encabezado), nunca el valor crudo (principio VI): el CSV puede
    traer de vuelta un teléfono en una columna mal puesta, y esa fila no lo imprime ni lo loggea."""
    fila: int
    motivo: str
