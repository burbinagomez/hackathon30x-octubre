from typing import Literal

CanalPublicado = Literal["whatsapp_comercial", "sitio_web", "osm_contacto", "whatsapp_osm"]
CONFIANZA_CANAL: dict[CanalPublicado, int] = {"whatsapp_comercial": 4, "sitio_web": 3, "osm_contacto": 2, "whatsapp_osm": 1}

Contacto = tuple[str, CanalPublicado]  # (valor, canal)


def elegir_canal(actual: Contacto | None, nuevo: Contacto | None) -> Contacto | None:
    """El nuevo reemplaza al actual solo si su canal tiene estrictamente más confianza."""
    return nuevo
