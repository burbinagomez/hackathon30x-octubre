"""Lectura del libro de costos para la pantalla (solo lectura, SQL inline, sin DDL). El tenant lo filtra la RLS de `costos`.

Nunca sale el lead_id: la pantalla solo necesita saber SI la fila es de un lead. lote_id = busqueda_id (el lote nace en la
búsqueda). Valor de lista = unidades x costo_unitario; el real descuenta lo que cayó en tier gratis.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo

TAMANO = 50

# `:b IS NULL OR lote_id = :b`: un solo texto de SQL con o sin filtro; el parámetro va tipado para que psycopg no infiera mal.
_FILTRO = "(CAST(:b AS uuid) IS NULL OR lote_id = CAST(:b AS uuid))"
_SQL_FILAS = text(f"""
    SELECT ts, tipo, fuente, proveedor, unidades, unidades * costo_unitario AS costo, gratis, lote_id,
           lead_id IS NOT NULL AS con_lead
    FROM costos WHERE {_FILTRO} ORDER BY ts DESC, id LIMIT :limite OFFSET :desde""")
_SQL_TOTAL = text(f"""
    SELECT count(*) AS filas, COALESCE(sum(unidades * costo_unitario), 0) AS lista,
           COALESCE(sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END), 0) AS real
    FROM costos WHERE {_FILTRO}""")
_SQL_POR_TIPO = text(f"""
    SELECT tipo, sum(unidades * costo_unitario) AS costo FROM costos WHERE {_FILTRO} GROUP BY tipo ORDER BY costo DESC, tipo""")
# Fuente nula = costo sin fuente; mismo nombre que el tablero.
_SQL_POR_FUENTE = text(f"""
    SELECT COALESCE(fuente, 'sin_atribuir') AS fuente, sum(unidades * costo_unitario) AS costo
    FROM costos WHERE {_FILTRO} GROUP BY 1 ORDER BY costo DESC, 1""")


@dataclass(frozen=True)
class FilaLibro:
    ts: datetime
    tipo: str
    fuente: str | None
    proveedor: str
    cantidad: Decimal
    costo_usd: Decimal
    gratis: bool
    lote_id: UUID | None
    con_lead: bool


@dataclass(frozen=True)
class PaginaLibro:
    items: tuple[FilaLibro, ...]
    total: int
    pagina: int
    tamano: int
    total_usd: Decimal
    total_real_usd: Decimal
    por_tipo: tuple[tuple[str, Decimal], ...]
    por_fuente: tuple[tuple[str, Decimal], ...]


def leer_libro(engine: Engine, tenant_id: UUID, pagina: int, busqueda_id: UUID | None = None) -> PaginaLibro:
    b = {"b": busqueda_id}
    with unidad_de_trabajo(engine, tenant_id) as c:
        filas = c.execute(_SQL_FILAS, {**b, "limite": TAMANO, "desde": (pagina - 1) * TAMANO}).all()
        t = c.execute(_SQL_TOTAL, b).one()
        por_tipo = c.execute(_SQL_POR_TIPO, b).all()
        por_fuente = c.execute(_SQL_POR_FUENTE, b).all()
    items = tuple(FilaLibro(f.ts, f.tipo, f.fuente, f.proveedor, f.unidades, f.costo, f.gratis, f.lote_id, f.con_lead)
                  for f in filas)
    return PaginaLibro(items, t.filas, pagina, TAMANO, t.lista, t.real,
                       tuple((r.tipo, r.costo) for r in por_tipo), tuple((r.fuente, r.costo) for r in por_fuente))
