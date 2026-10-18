"""Buscador de sitio web (enmienda 2026-10-18 de la spec 006): de la razón social salen pocos dominios candidatos y se
acepta uno solo si la página prueba que es de esa empresa. Puro: sin red, sin base.

Es una decisión de cumplimiento, no una utilidad: un dominio aceptado de más es contactar a otra empresa. Por eso el
candidato es solo una hipótesis y `verifica_pagina` es la única puerta.
"""
import html
import re
import unicodedata

from app.modulos.enriquecimiento.dominio.normalizar_titular import normalizar_nombre

MAX_CANDIDATOS = 6
TLDS = ("com.co", "com", "co")
MIN_DIGITOS_NIT = 7  # un NIT colombiano tiene 8-10 dígitos sin DV; menos es ruido y daría falsos positivos

# Palabras que solas no identifican a nadie. Un dominio hecho solo de ellas no se prueba.
GENERICAS = frozenset({
    "COMERCIAL", "COMERCIALIZADORA", "GRUPO", "INVERSIONES", "SERVICIOS", "SERVICIO", "EMPRESA", "COMPANIA", "CIA",
    "CORPORACION", "FUNDACION", "ASOCIACION", "DISTRIBUIDORA", "DISTRIBUCIONES", "INDUSTRIAS", "INDUSTRIA", "SOLUCIONES",
    "TRANSPORTES", "TRANSPORTE", "LOGISTICA", "INTERNACIONAL", "NACIONAL", "COLOMBIA", "COLOMBIANA", "GLOBAL", "GENERAL",
    "NEGOCIOS", "PROYECTOS", "CONSTRUCCIONES", "INMOBILIARIA", "REPRESENTACIONES", "IMPORTACIONES", "EXPORTACIONES",
    "DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "E", "AND", "THE", "GROUP", "SERVICES",
})
_ESTADOS = (("EN", "LIQUIDACION"), ("EN", "REORGANIZACION"))


def razon_social_limpia(razon_social: str) -> list[str]:
    """Palabras en mayúsculas, sin tildes ni puntuación, sin sufijo societario ni `EN LIQUIDACION`/`EN REORGANIZACION`."""
    palabras = normalizar_nombre(razon_social).split()
    cambio = True
    while cambio and palabras:
        cambio = False
        for estado in _ESTADOS:
            for i in range(len(palabras) - 1):
                if tuple(palabras[i:i + 2]) == estado:
                    del palabras[i:i + 2]
                    cambio = True
                    break
        limpio = normalizar_nombre(" ".join(palabras)).split()
        cambio = cambio or limpio != palabras
        palabras = limpio
    return palabras


def candidatos_de_dominio(razon_social: str) -> tuple[str, ...]:
    palabras = [p.lower() for p in razon_social_limpia(razon_social)]
    if not palabras or all(p.upper() in GENERICAS for p in palabras):
        return ()
    variantes = ["".join(palabras)]
    if len(palabras) > 3 and not all(p.upper() in GENERICAS for p in palabras[:2]):
        variantes.append("".join(palabras[:2]))
    if len(palabras) > 1:
        variantes.append("-".join(palabras))
    candidatos = dict.fromkeys(f"{v}.{tld}" for v in variantes if 3 <= len(v) <= 63 for tld in TLDS)
    return tuple(candidatos)[:MAX_CANDIDATOS]


def _texto_plano(pagina: str) -> str:
    sin_etiquetas = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>|<[^>]*>", " ", pagina)
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", html.unescape(sin_etiquetas)) if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()) + " "


def _menciona_nit(pagina: str, nit: str) -> bool:
    agrupado = f"{int(nit):,}".replace(",", ".")  # 900123456 -> 900.123.456
    return any(re.search(rf"(?<![\d.]){re.escape(forma)}(?!\d)", pagina) for forma in (nit, agrupado))


def verifica_pagina(pagina: str, nit: str | None, razon_social: str) -> str | None:
    """`nit` (sin DV, con o sin puntos), `razon_social` (completa, sin sufijo, como palabras enteras) o None."""
    digitos = re.sub(r"\D", "", nit or "")
    if len(digitos) >= MIN_DIGITOS_NIT and _menciona_nit(html.unescape(pagina), digitos):
        return "nit"
    palabras = [p.lower() for p in razon_social_limpia(razon_social)]
    if palabras and f" {' '.join(palabras)} " in _texto_plano(pagina):
        return "razon_social"
    return None
