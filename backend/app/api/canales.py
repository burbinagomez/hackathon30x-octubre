from collections.abc import Mapping


def canal_habilitado(canal: str, canales_contacto: Mapping[str, Mapping]) -> bool:
    """canal_preferido es válido si alguna entrada habilitada de `canales_contacto` lo declara en su clave `canal`.

    Se lee del YAML en cada validación: habilitar un canal es un flag, no un cambio de código.
    """
    return any(e.get("habilitado") and e.get("canal") == canal for e in canales_contacto.values())
