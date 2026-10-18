import re
import unicodedata

# Sufijos societarios al final del nombre: "Éxito S.A." y "Exito" son la misma empresa.
_SUFIJOS = frozenset({"sas", "sa", "ltda", "ltd", "eu", "sca", "scs"})


def normalizar_nombre(texto: str) -> str:
    """Clave de comparación de un nombre de empresa: sin tildes, minúsculas, sin puntuación ni sufijo societario."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    # Los puntos se borran (S.A.S. -> sas); el resto de la puntuación separa palabras.
    palabras = re.sub(r"[^a-z0-9]+", " ", sin_tildes.casefold().replace(".", "")).split()
    while palabras and palabras[-1] in _SUFIJOS:
        palabras.pop()
    return " ".join(palabras)
