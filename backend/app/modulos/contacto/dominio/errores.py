class SinBaseLegal(Exception):
    """El contacto no tiene `cumplimiento.base_legal` al momento de enviar."""


class CanalNoDisponible(Exception):
    """Error de transporte. El mensaje nunca lleva la dirección."""


class SinVistaPrevia(Exception):
    """`enviar` sin un `--dry-run` previo de esa búsqueda (P1)."""


class MensajeCambio(Exception):
    """El `mensaje_base` de la búsqueda cambió desde el `--dry-run`: hace falta otro."""


class PlantillaInvalida(Exception):
    """El mensaje no cumple la regla 7. `args[0]` es el nombre de la regla."""


class DestinatarioInvalido(Exception):
    """La dirección no es una sola casilla o un encabezado trae CR/LF. Nunca se reintenta ni se cobra."""
