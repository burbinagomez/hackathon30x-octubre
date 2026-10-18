from dataclasses import asdict
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo
from app.modulos.calificacion.dominio.modelos import ResultadoCalificacion
from app.modulos.costos.dominio.modelos import OperacionCosto

_LEAD = text(
    "SELECT l.tipo_titular = 'juridica' AND c.lead_id IS NOT NULL AS cumple "
    "FROM leads l LEFT JOIN cumplimiento c ON c.tenant_id = l.tenant_id AND c.lead_id = l.id "
    "WHERE l.id = :lead_id"
)
_EXISTENTE = text("SELECT calificado, minutos FROM calificaciones WHERE tenant_id = :t AND lead_id = :lead_id")
_INSERT_CALIFICACION = text(
    "INSERT INTO calificaciones (tenant_id, lead_id, calificado, calificado_en, minutos) "
    "VALUES (:t, :lead_id, :calificado, :fecha, :minutos)"
)
# No se reutiliza PostgresCostos.registrar(): abre su propia transacción y acá el costo tiene que
# escribirse en la MISMA transacción que la calificación (T010: si uno falla, el otro no queda).
_INSERT_COSTO = text(
    "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, canal, lead_id, "
    "lote_id, gratis, ts) VALUES (:t, :tipo, :unidades, :costo_unitario, :moneda, :proveedor, :fuente, :canal, "
    ":lead_id, :lote_id, :gratis, COALESCE(CAST(:ts AS timestamptz), now()))"
)


class PostgresCalificaciones:
    """Calificación + `dapta_llamada` en costos, en una sola transacción (T011). RLS filtra los leads de otro
    tenant por sí sola: un lead que no aparece en el SELECT (de otro tenant o inexistente) es `ref_desconocida`."""

    def __init__(self, engine: Engine, tenant_id: UUID):
        self._engine = engine
        self._tenant_id = tenant_id

    def guardar(self, resultado: ResultadoCalificacion, costo: OperacionCosto) -> str:
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            fila = c.execute(_LEAD, {"lead_id": resultado.lead_id}).one_or_none()
            if fila is None:
                return "ref_desconocida"
            if not fila.cumple:
                return "no_cumple"

            existente = c.execute(_EXISTENTE, {"t": self._tenant_id, "lead_id": resultado.lead_id}).one_or_none()
            if existente is not None:
                if (existente.calificado, existente.minutos) == (resultado.calificado, resultado.minutos):
                    return "duplicada"
                return "conflicto"

            c.execute(_INSERT_CALIFICACION, {"t": self._tenant_id, "lead_id": resultado.lead_id,
                                             "calificado": resultado.calificado, "fecha": resultado.fecha,
                                             "minutos": resultado.minutos})
            c.execute(_INSERT_COSTO, {"t": self._tenant_id, **asdict(costo)})
            return "importada"
