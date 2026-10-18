class ArchivoInvalido(ValueError):
    """El archivo de resultados supera el límite de filas (plan.md: ≤ 1000). Se corta antes de tocar una fila."""


class TarifaPendiente(RuntimeError):
    """`dapta.usd_por_minuto` es `null` en config/tarifas.yaml: el import no escribe nada (plan.md)."""
