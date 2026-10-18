"""Mensaje de primer contacto con el pie de la regla 7 (identificación, origen del dato, baja, privacidad)."""

from app.modulos.contacto.dominio.errores import PlantillaInvalida

ORIGENES = {
    "sitio_web": "encontramos su contacto en su sitio web",
    "osm_contacto": "encontramos su contacto en un directorio público (OpenStreetMap)",
}


def componer(mensaje_base: str, remitente: str, canal_origen: str, url_baja: str,
             url_privacidad: str) -> tuple[str, str]:
    """(asunto, cuerpo) con el pie completo y el enlace de baja."""
    if canal_origen not in ORIGENES:
        raise PlantillaInvalida("origen")
    asunto = " ".join(f"Consulta de {remitente}".split())
    cuerpo = (
        f"{mensaje_base.strip()}\n\n"
        f"--\n{remitente}. Le escribimos porque {ORIGENES[canal_origen]}.\n"
        f"Si no quiere recibir más mensajes, responda BAJA o use este enlace: {url_baja}\n"
        f"Privacidad: {url_privacidad}\n"
    )
    return asunto, cuerpo


def validar(cuerpo: str, remitente: str, url_baja: str, url_privacidad: str) -> None:
    """Regla 7 de cumplimiento: lanza PlantillaInvalida con el nombre de la regla que falla."""
    if remitente not in cuerpo:
        raise PlantillaInvalida("identificacion")
    if not any(o in cuerpo for o in ORIGENES.values()):
        raise PlantillaInvalida("origen")
    if "BAJA" not in cuerpo or {t for t in cuerpo.split() if "/baja/" in t} != {url_baja}:
        raise PlantillaInvalida("baja")
    if url_privacidad not in cuerpo:
        raise PlantillaInvalida("privacidad")
    if len(cuerpo.split()) >= 100:
        raise PlantillaInvalida("palabras")
    if cuerpo.count("?") > 1:
        raise PlantillaInvalida("preguntas")
