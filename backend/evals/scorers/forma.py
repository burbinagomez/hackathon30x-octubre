"""Scorers de forma deterministas. Devuelven el nombre de la regla que falla, o None si la forma pasa.

El runner lo usa como motivo `forma:<regla>`. Las reglas del mensaje son la regla 7 de cumplimiento-datos;
en la 007 pasan al dominio (`plantilla`) y esto queda como envoltorio.
"""
import re

# ponytail: detección por frases fijas en es/en; si la 007 cambia la plantilla, se ajustan acá.
OPT_OUT = re.compile(r"\b(BAJA|STOP)\b")
ORIGEN_DEL_DATO = re.compile(r"encontramos su (contacto|correo|n[uú]mero)|we found your (contact|email|number)", re.I)
PRIVACIDAD = "/privacidad"


def encaje(salida) -> str | None:
    p = salida.get("probabilidad") if isinstance(salida, dict) else None
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        return "probabilidad"
    if not 0 <= p <= 1:
        return "rango"
    return None


def mensaje(msg) -> str | None:
    cuerpo = msg.get("cuerpo") or ""
    if len(cuerpo.split()) >= 100:
        return "palabras"
    if not OPT_OUT.search(cuerpo):
        return "opt_out"
    if not ORIGEN_DEL_DATO.search(cuerpo):
        return "origen_del_dato"
    if cuerpo.count("?") > 1:  # ¿…? cuenta una
        return "preguntas"
    if msg.get("adjuntos") != []:
        return "adjuntos"
    if PRIVACIDAD not in cuerpo:
        return "privacidad"
    return None
