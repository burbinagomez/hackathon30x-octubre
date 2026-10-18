"""Solo lee vistas (módulo sin dominio a propósito: la lógica vive en SQL). El tenant lo filtra la RLS vía security_invoker."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo


@dataclass(frozen=True)
class FilaFuente:
    fuente: str
    encontrados: int
    unicos: int


@dataclass(frozen=True)
class Atribucion:
    fuente: str
    texto: str
    url: str


@dataclass(frozen=True)
class DatosTablero:
    fuentes: tuple[FilaFuente, ...]
    total: FilaFuente
    atribuciones: tuple[Atribucion, ...]


def leer_tablero(engine: Engine, tenant_id: UUID) -> DatosTablero:
    with unidad_de_trabajo(engine, tenant_id) as c:
        filas = [FilaFuente(f.fuente, f.encontrados, f.unicos) for f in c.execute(
            text("SELECT fuente, encontrados, unicos FROM v_tablero_fuentes ORDER BY fuente"))]
        atribuciones = tuple(Atribucion(a.fuente, a.texto, a.url) for a in c.execute(
            text("SELECT fuente, texto, url FROM v_atribuciones ORDER BY orden")))
    # La vista da la fila TOTAL solo si hay datos (HAVING); sin datos, ceros.
    total = next((f for f in filas if f.fuente == "TOTAL"), FilaFuente("TOTAL", 0, 0))
    return DatosTablero(tuple(f for f in filas if f.fuente != "TOTAL"), total, atribuciones)
