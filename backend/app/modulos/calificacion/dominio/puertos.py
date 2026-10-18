from typing import Protocol

from app.modulos.calificacion.dominio.modelos import FilaRechazada, ResultadoCalificacion


class Calificador(Protocol):
    def leer_resultados(self, archivo: bytes) -> list[ResultadoCalificacion | FilaRechazada]:
        """Lanza `ArchivoInvalido` si el archivo supera el límite de filas, antes de tocar una fila."""
        ...


class RepositorioCalificaciones(Protocol):
    def guardar(self, resultado: ResultadoCalificacion, costo) -> str:
        """Calificación y `dapta_llamada` en la misma transacción (si corresponde). Devuelve:

        `importada` | `duplicada` (mismo resultado ya estaba) | `conflicto` (otro resultado ya estaba, no cambia
        nada) | `no_cumple` (no es `juridica` o no tiene fila en `cumplimiento`) | `ref_desconocida` (el lead no
        existe para este tenant, o es de otro y RLS no lo distingue, a propósito).
        """
        ...
