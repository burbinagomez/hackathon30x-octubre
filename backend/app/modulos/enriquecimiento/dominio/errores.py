class IPPrivadaRechazada(ValueError):
    """El dominio resuelve a una IP privada, loopback, link-local o reservada. Se lanza antes de cualquier request."""


class DemasiadasRedirecciones(RuntimeError):
    """Más de 3 saltos de redirección."""


class SalidaJevInvalida(ValueError):
    """jev devolvió una etiqueta fuera del enum o una probabilidad fuera de [0,1]. El costo ya quedó registrado."""
