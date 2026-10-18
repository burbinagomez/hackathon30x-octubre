"""Forma de la sugerencia: el body de `PedidoVistaPrevia` sin tope/canal/mensaje (spec 010, ajuste 1).

Copia de la definición de la rama de la Puerta B; el merge las unifica en `sugerencia.py`.
`departamento` y `ciudad` son códigos nativos de config/geografia, nunca texto libre; `ciiu` está en el catálogo o es None.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Sugerencia:
    pais: str = "CO"
    ciiu: str | None = None
    departamento: str | None = None
    ciudad: str | None = None
    ingresos_min: int | None = None
    palabras_clave: tuple[str, ...] = ()
    exclusiones: tuple[str, ...] = ()
