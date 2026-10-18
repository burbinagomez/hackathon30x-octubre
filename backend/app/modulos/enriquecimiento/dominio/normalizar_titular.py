"""Normalización de la regla "nombre + ciudad" (enmienda 2026-10-18 de la spec 006).

Es una decisión de cumplimiento, no una utilidad: lo que acá se considere "el mismo nombre" decide quién pasa a
jurídica y se contacta. Por eso vive aparte de la de intake (que busca candidatos, no decide) y está fijada por tests.
"""
import re
import unicodedata

# Sufijos societarios que se ignoran al final del nombre, ya sin puntos (S.A.S. -> SAS). OSM casi nunca los trae y el
# RUES siempre; la unicidad por NIT evita que "X LTDA" y "X SAS" se confundan.
_SUFIJOS = frozenset({"SAS", "SA", "LTDA", "LTD", "EU", "SCA", "SCS"})


def _palabras(texto: str) -> list[str]:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    # Los puntos se borran (S.A.S. -> SAS); el resto de la puntuación separa palabras.
    return re.sub(r"[^A-Z0-9]+", " ", sin_tildes.upper().replace(".", "")).split()


def normalizar_nombre(texto: str) -> str:
    palabras = _palabras(texto)
    while palabras and palabras[-1] in _SUFIJOS:
        palabras.pop()
    return " ".join(palabras)


def normalizar_ciudad(texto: str) -> str:
    """Igual que el nombre, sin sufijos societarios, pero un `D.C.` final se ignora (Bogotá D.C. = Bogotá)."""
    palabras = _palabras(texto)
    if palabras[-1:] == ["DC"] or palabras[-2:] == ["D", "C"]:
        del palabras[-1 if palabras[-1] == "DC" else -2:]
    return " ".join(palabras)
