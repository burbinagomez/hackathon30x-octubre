"""Validación de una fila de resultados, independiente del formato de archivo (CSV real, lo que sea un doble de
pruebas): cada adaptador del puerto `Calificador` decodifica su propio formato a un `dict[str, str]` y llama
a `mapear_fila`. Así el criterio de rechazo vive en un solo lugar (principio I: dominio sin framework)."""
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.modulos.calificacion.dominio.modelos import FilaRechazada, ResultadoCalificacion

COLUMNAS = {"lead_id", "calificado", "fecha", "minutos"}


def mapear_fila(numero: int, fila: Mapping[str, str], ahora: datetime) -> ResultadoCalificacion | FilaRechazada:
    if not COLUMNAS <= fila.keys():
        return FilaRechazada(numero, "falta_columna")
    try:
        lead_id = UUID(fila["lead_id"])
        if fila["calificado"] not in ("si", "no"):
            return FilaRechazada(numero, "valor_invalido")
        calificado = fila["calificado"] == "si"
        fecha = datetime.fromisoformat(fila["fecha"])
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=UTC)
        minutos = Decimal(str(fila["minutos"]))
    except (ValueError, InvalidOperation, KeyError, TypeError):
        return FilaRechazada(numero, "valor_invalido")
    if fecha > ahora:
        return FilaRechazada(numero, "fecha_futura")
    if not (0 <= minutos <= 60):
        return FilaRechazada(numero, "minutos_fuera_de_rango")
    return ResultadoCalificacion(lead_id, calificado, fecha, minutos)
