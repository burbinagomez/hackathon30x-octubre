"""JuezFalso: doble para los tests del runner. Sin red ni RegistroCostos (exclusión cerrada)."""
from collections import Counter

from evals.jueces.puerto import Veredicto


class JuezFalso:
    determinista_si_se_demuestra = False

    def __init__(self, secuencias: dict):
        self.llamadas: Counter[str] = Counter()

    def juzgar(self, tarea: str, caso: dict) -> Veredicto:
        return Veredicto(-1.0, "")
