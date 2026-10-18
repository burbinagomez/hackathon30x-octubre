class IPPrivadaRechazada(ValueError):
    """El dominio resuelve a una IP privada, loopback, link-local o reservada. Se lanza antes de cualquier request."""


class DemasiadasRedirecciones(RuntimeError):
    """Más de 3 saltos de redirección."""


class SalidaJevInvalida(ValueError):
    """jev devolvió una etiqueta fuera del enum o una probabilidad fuera de [0,1]. El costo ya quedó registrado."""


class UsoJevInvalido(RuntimeError):
    """jev no informó tokens_in medibles (falta, no es entero o es negativo). El techo ya quedó cobrado."""


class JevNoDisponible(RuntimeError):
    """jev respondió 5xx o no respondió a tiempo. El costo ya quedó registrado; la falla cuenta solo contra ese lead."""
