from collections.abc import Mapping


def canal_habilitado(canal: str, canales_contacto: Mapping[str, Mapping]) -> bool:
    """canal_preferido es válido si alguna entrada habilitada de `canales_contacto` lo declara en su clave `canal`."""
    return False  # esqueleto T032
