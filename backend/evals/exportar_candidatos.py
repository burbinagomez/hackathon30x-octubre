"""Esqueleto T020: exporta los leads de una búsqueda a dataset.candidatos.json. T021 lo implementa."""
import json
from pathlib import Path
from typing import NamedTuple
from uuid import UUID
from datetime import datetime

SALIDA = Path(__file__).resolve().parent / "dataset.candidatos.json"


class Origen(NamedTuple):
    """Una fila de lead_fuentes de la búsqueda, con los rasgos del lead que el Lead del 002 no trae."""
    lead_id: UUID
    fuente: str
    as_of: datetime
    licencia: str
    actividad: str | None = None
    ingresos_cop: int | None = None


def main(argv=None, *, repo=None, listar=None, salida: Path = SALIDA) -> int:
    salida.write_text(json.dumps({"casos": []}))  # esqueleto T020
    return 0
