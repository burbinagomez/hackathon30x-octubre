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
    # Embudo: solo conteos de leads únicos de la fuente. None = no aplica (costo sin fuente), nunca un 0 inventado.
    enriquecidos: int | None = None
    contactables: int | None = None
    con_telefono: int | None = None
    calificados: int | None = None


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
    costo_intake: Decimal | None = None


# Costo por fuente desde `costos` (lista = unidades x tarifa; real = 0 si cayó en tier gratis). Lo de evals (desarrollo) y
# lo de intake (calibración: la Puerta B, sin lead ni búsqueda) va aparte y no entra al costo de adquisición.
# Sin vistas nuevas a propósito: no hay DDL, es SQL inline.
# La fuente nula es `sin_atribuir`. CPL = costo / únicos: NULLIF evita la división por cero y deja NULL ("sin dato").
# El tenant lo filtra la RLS de `costos` y de la vista (security_invoker): no hay `WHERE tenant_id`.
# Embudo (enriquecidos, contactables, con teléfono, calificados): leads distintos por fuente, así que un lead de dos fuentes
# suma en las dos y el total no duplica. Solo conteos: jamás se selecciona un dato de contacto. La RLS de leads,
# lead_fuentes y calificaciones filtra el tenant. `sin_atribuir` es costo sin lead: el embudo no le aplica (NULL).
_EMBUDO = """count(DISTINCT lf.lead_id) FILTER (WHERE l.enriquecido_en IS NOT NULL) AS enriquecidos,
               count(DISTINCT lf.lead_id) FILTER (WHERE l.contactable) AS contactables,
               count(DISTINCT lf.lead_id) FILTER (WHERE l.tipo_titular = 'juridica' AND l.telefono_cifrado IS NOT NULL) AS con_telefono,
               count(DISTINCT lf.lead_id) FILTER (WHERE q.calificado) AS calificados"""
_DESDE_EMBUDO = """FROM lead_fuentes lf
          JOIN leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
          LEFT JOIN calificaciones q ON q.tenant_id = lf.tenant_id AND q.lead_id = lf.lead_id"""
_SQL_FUENTES = text(f"""
    WITH c AS (
      SELECT COALESCE(fuente, 'sin_atribuir') AS fuente,
             sum(unidades * costo_unitario) AS lista,
             sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END) AS real
      FROM costos WHERE fuente IS DISTINCT FROM 'evals' AND fuente IS DISTINCT FROM 'intake' GROUP BY 1),
    t AS (SELECT fuente, encontrados, unicos FROM v_tablero_fuentes WHERE fuente <> 'TOTAL'),
    e AS (SELECT lf.fuente, {_EMBUDO}
          {_DESDE_EMBUDO} GROUP BY lf.fuente),
    f AS (
      SELECT COALESCE(t.fuente, c.fuente) AS fuente, COALESCE(t.encontrados, 0) AS encontrados,
             COALESCE(t.unicos, 0) AS unicos, c.lista, c.real
      FROM t FULL JOIN c ON c.fuente = t.fuente)
    SELECT f.fuente, encontrados, unicos, lista, real, lista / NULLIF(unicos, 0) AS cpl_lista,
           real / NULLIF(unicos, 0) AS cpl_real,
           CASE WHEN f.fuente = 'sin_atribuir' THEN NULL ELSE COALESCE(e.enriquecidos, 0) END AS enriquecidos,
           CASE WHEN f.fuente = 'sin_atribuir' THEN NULL ELSE COALESCE(e.contactables, 0) END AS contactables,
           CASE WHEN f.fuente = 'sin_atribuir' THEN NULL ELSE COALESCE(e.con_telefono, 0) END AS con_telefono,
           CASE WHEN f.fuente = 'sin_atribuir' THEN NULL ELSE COALESCE(e.calificados, 0) END AS calificados
    FROM f LEFT JOIN e ON e.fuente = f.fuente ORDER BY f.fuente""")
_SQL_EMBUDO_TOTAL = text(f"""
    SELECT {_EMBUDO}
          {_DESDE_EMBUDO}""")
_SQL_TOTAL = text("""
    WITH k AS (
      SELECT COALESCE((SELECT encontrados FROM v_tablero_fuentes WHERE fuente = 'TOTAL'), 0) AS encontrados,
             COALESCE((SELECT unicos FROM v_tablero_fuentes WHERE fuente = 'TOTAL'), 0) AS unicos,
             (SELECT sum(unidades * costo_unitario) FROM costos WHERE fuente IS DISTINCT FROM 'evals' AND fuente IS DISTINCT FROM 'intake') AS lista,
             (SELECT sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END) FROM costos
               WHERE fuente IS DISTINCT FROM 'evals' AND fuente IS DISTINCT FROM 'intake') AS real,
             (SELECT sum(unidades * costo_unitario) FROM costos WHERE fuente = 'evals') AS evals,
             (SELECT sum(unidades * costo_unitario) FROM costos WHERE fuente = 'intake') AS intake)
    SELECT *, lista / NULLIF(unicos, 0) AS cpl_lista, real / NULLIF(unicos, 0) AS cpl_real FROM k""")


def leer_tablero(engine: Engine, tenant_id: UUID) -> DatosTablero:
    with unidad_de_trabajo(engine, tenant_id) as c:
        filas = tuple(FilaFuente(f.fuente, f.encontrados, f.unicos, f.lista, f.real, f.cpl_lista, f.cpl_real,
                      f.enriquecidos, f.contactables, f.con_telefono, f.calificados)
                      for f in c.execute(_SQL_FUENTES))
        t = c.execute(_SQL_TOTAL).one()
        e = c.execute(_SQL_EMBUDO_TOTAL).one()
        atribuciones = tuple(Atribucion(a.fuente, a.texto, a.url) for a in c.execute(
            text("SELECT fuente, texto, url FROM v_atribuciones ORDER BY orden")))
    total = FilaFuente("TOTAL", t.encontrados, t.unicos, t.lista, t.real, t.cpl_lista, t.cpl_real,
                       e.enriquecidos, e.contactables, e.con_telefono, e.calificados)
    return DatosTablero(filas, total, atribuciones, t.evals, t.intake)
