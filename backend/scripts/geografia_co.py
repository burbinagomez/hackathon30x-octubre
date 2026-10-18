"""Genera config/geografia/co.yaml. NO corre en runtime ni en CI: se corre a mano y el YAML se versiona."""

DEPARTAMENTOS: list[tuple[str, str, str, str]] = []  # esqueleto


def construir(filas: list[dict], fecha: str, dataset: str | None) -> str:
    return ""  # esqueleto
