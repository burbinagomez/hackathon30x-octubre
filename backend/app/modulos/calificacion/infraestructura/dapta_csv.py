import csv
import io
from datetime import UTC, datetime

from app.modulos.calificacion.dominio.errores import ArchivoInvalido
from app.modulos.calificacion.dominio.mapeo import mapear_fila
from app.modulos.calificacion.dominio.modelos import FilaRechazada, ResultadoCalificacion

LIMITE_FILAS = 1000  # plan.md. El límite de 1 MB se corta en el endpoint (app/api/calificaciones.py),
# leyendo el stream antes de que el cuerpo llegue a este adaptador.


class DaptaCSV:
    """Adaptador del puerto `Calificador` para el CSV de resultados de Dapta (plan.md, mínimo de demo)."""

    def leer_resultados(self, archivo: bytes) -> list[ResultadoCalificacion | FilaRechazada]:
        try:
            texto = archivo.decode("utf-8-sig")  # con o sin BOM
        except UnicodeDecodeError:
            raise ArchivoInvalido("no es UTF-8") from None
        filas = list(csv.DictReader(io.StringIO(texto)))
        if len(filas) > LIMITE_FILAS:
            raise ArchivoInvalido(f"más de {LIMITE_FILAS} filas")
        ahora = datetime.now(UTC)
        return [mapear_fila(i, fila, ahora) for i, fila in enumerate(filas, start=1)]
