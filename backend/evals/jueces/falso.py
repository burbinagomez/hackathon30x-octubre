"""JuezFalso: doble para los tests del runner. Sin red ni RegistroCostos (exclusión cerrada)."""
from collections import Counter

from evals.jueces.puerto import Veredicto


class JuezFalso:
    determinista_si_se_demuestra = False

    def __init__(self, secuencias: dict[str, list]):
        # Por id de caso: probabilidades en orden, o una excepción (p. ej. SalidaJuezInvalida) que se lanza.
        self._pendientes = {id_: list(s) for id_, s in secuencias.items()}
        self.llamadas: Counter[str] = Counter()

    def juzgar(self, tarea: str, caso: dict) -> Veredicto:
        self.llamadas[caso["id"]] += 1
        siguiente = self._pendientes[caso["id"]].pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return Veredicto(siguiente, "falso")
