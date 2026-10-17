class CriterioNoSoportado(ValueError):
    """Un filtro de los criterios no está en meta.filtros. Se lanza antes de cualquier request."""


class LimiteFuenteAgotado(RuntimeError):
    """El límite de 24 h llegó antes de un intento, o la fuente respondió 429."""


class FuenteNoDisponible(RuntimeError):
    """Los intentos fallaron. Las filas de costos ya quedaron escritas."""


class RegistroInvalido(ValueError):
    """fuentes.yaml no cumple lo que exige el registro."""
