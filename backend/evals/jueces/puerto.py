"""Puerto del juez de significado: un caso por llamada, nunca un array referenciado por posición."""
from dataclasses import dataclass
from typing import ClassVar, Protocol


@dataclass(frozen=True)
class Veredicto:
    # Sin validar rango: lo valida el adaptador al parsear la salida (y el stub de T013 lo necesita fuera de rango).
    probabilidad: float
    razon: str


class SalidaJuezInvalida(Exception):
    """La salida del juez no respeta el esquema {probabilidad: number en [0,1], razon: string}."""


class ErrorJuez(Exception):
    """El juez no respondió (HTTP 4xx/5xx o red). Mensaje = código (`http_401`, `red`), sin cadena de causa:
    la excepción de httpx lleva request.headers (la key) y response.text."""


class Juez(Protocol):
    # True solo si el juez puede bajar a k=1 tras demostrar determinación a k=3 (jev, en la 006).
    determinista_si_se_demuestra: ClassVar[bool]

    def juzgar(self, tarea: str, caso: dict) -> Veredicto: ...
