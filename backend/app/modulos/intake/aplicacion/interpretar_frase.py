from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modulos.intake.dominio.sugerencia import Sugerencia


@dataclass(frozen=True)
class ResultadoFrase:
    sugerencia: Sugerencia
    costo_usd: Decimal
    lote_id: UUID


class InterpretarFrase:
    def __init__(self, generador, costos, geografia, actividades, nuevo_lote=None):
        pass

    def ejecutar(self, frase: str) -> ResultadoFrase:
        return ResultadoFrase(Sugerencia(pais="CO"), Decimal(0), UUID(int=0))
