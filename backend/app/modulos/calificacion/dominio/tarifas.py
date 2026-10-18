from decimal import ROUND_CEILING, Decimal


def minutos_facturables(minutos: Decimal) -> Decimal:
    """Dapta cobra el minuto contestado completo, redondeado hacia arriba (docs.dapta.ai, Billing and credits)."""
    return minutos.to_integral_value(rounding=ROUND_CEILING)
