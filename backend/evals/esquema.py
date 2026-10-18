"""Esquema y whitelist de los JSON versionados en evals/ (el repo es público)."""

RANGOS_INGRESOS = ("micro", "pequena", "mediana", "grande")


def problemas_contacto(archivo: str, datos) -> list[str]:
    return ["no_implementado"]


def problemas_dataset(datos) -> list[str]:
    return ["no_implementado"]


def rango_ingresos(cop: int) -> str:
    return "no_implementado"
