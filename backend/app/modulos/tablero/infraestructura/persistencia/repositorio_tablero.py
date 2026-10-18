"""Solo lee vistas (módulo sin dominio a propósito: la lógica vive en SQL). El tenant lo filtra la RLS vía security_invoker."""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo


@dataclass(frozen=True)
class FilaFuente:
    fuente: str
    encontrados: int
    unicos: int
    costo_lista: Decimal | None = None
    costo_real: Decimal | None = None
    cpl_lista: Decimal | None = None
    cpl_real: Decimal | None = None


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
    costo_evals: Decimal | None = None


# Costo por fuente desde `costos` (lista = unidades x tarifa; real = 0 si cayó en tier gratis). Lo de evals va aparte.
# La fuente nula es `sin_atribuir`. CPL = costo / únicos: NULLIF evita la división por cero y deja NULL ("sin dato").
# El tenant lo filtra la RLS de `costos` y de la vista (security_invoker): no hay `WHERE tenant_id`.
_SQL_FUENTES = text("""
    WITH c AS (
      SELECT COALESCE(fuente, 'sin_atribuir') AS fuente,
             sum(unidades * costo_unitario) AS lista,
             sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END) AS real
      FROM costos WHERE fuente IS DISTINCT FROM 'evals' GROUP BY 1),
    t AS (SELECT fuente, encontrados, unicos FROM v_tablero_fuentes WHERE fuente <> 'TOTAL'),
    f AS (
      SELECT COALESCE(t.fuente, c.fuente) AS fuente, COALESCE(t.encontrados, 0) AS encontrados,
             COALESCE(t.unicos, 0) AS unicos, c.lista, c.real
      FROM t FULL JOIN c ON c.fuente = t.fuente)
    SELECT fuente, encontrados, unicos, lista, real, lista / NULLIF(unicos, 0) AS cpl_lista,
           real / NULLIF(unicos, 0) AS cpl_real
    FROM f ORDER BY fuente""")
_SQL_TOTAL = text("""
    WITH k AS (
      SELECT COALESCE((SELECT encontrados FROM v_tablero_fuentes WHERE fuente = 'TOTAL'), 0) AS encontrados,
             COALESCE((SELECT unicos FROM v_tablero_fuentes WHERE fuente = 'TOTAL'), 0) AS unicos,
             (SELECT sum(unidades * costo_unitario) FROM costos WHERE fuente IS DISTINCT FROM 'evals') AS lista,
             (SELECT sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END) FROM costos
               WHERE fuente IS DISTINCT FROM 'evals') AS real,
             (SELECT sum(unidades * costo_unitario) FROM costos WHERE fuente = 'evals') AS evals)
    SELECT *, lista / NULLIF(unicos, 0) AS cpl_lista, real / NULLIF(unicos, 0) AS cpl_real FROM k""")


def leer_tablero(engine: Engine, tenant_id: UUID) -> DatosTablero:
    with unidad_de_trabajo(engine, tenant_id) as c:
        filas = tuple(FilaFuente(f.fuente, f.encontrados, f.unicos, f.lista, f.real, f.cpl_lista, f.cpl_real)
                      for f in c.execute(_SQL_FUENTES))
        t = c.execute(_SQL_TOTAL).one()
        atribuciones = tuple(Atribucion(a.fuente, a.texto, a.url) for a in c.execute(
            text("SELECT fuente, texto, url FROM v_atribuciones ORDER BY orden")))
    total = FilaFuente("TOTAL", t.encontrados, t.unicos, t.lista, t.real, t.cpl_lista, t.cpl_real)
    return DatosTablero(filas, total, atribuciones, t.evals)
