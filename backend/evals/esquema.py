"""Esquema y whitelist de los JSON versionados en evals/ (el repo es público)."""

RANGOS_INGRESOS = ("micro", "pequena", "mediana", "grande")


def problemas_contacto(archivo: str, datos) -> list[str]:
    return ["no_implementado"]


def problemas_dataset(datos) -> list[str]:
    return ["no_implementado"]


def rango_ingresos(cop: int) -> str:
    """Bucket de ingresos anuales en pesos COP (no miles), los que reporta Supersociedades."""
    return "no_implementado"
