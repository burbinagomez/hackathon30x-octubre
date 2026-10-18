import json
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, EmpresaCruda, Lead
from app.seguridad.cifrado import Cifrador

_INSERT_LEAD = text(
    "INSERT INTO leads (tenant_id, pais, id_fiscal, nombre, tipo_titular, ciudad, direccion, "
    "actividad_codigo, actividad_sistema, web) "
    "VALUES (:t, :pais, :id_fiscal, :nombre, :tipo_titular, :ciudad, :direccion, :codigo, :sistema, :web) "
    "ON CONFLICT (tenant_id, pais, id_fiscal) DO NOTHING RETURNING id"
)
_INSERT_CUMPLIMIENTO = text(
    "INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
    "VALUES (:t, :lead_id, :fuente, :licencia, :url_origen, :as_of)"
)


class RepositorioLeadsPostgres:
    """Cada método abre su propia unidad de trabajo con el tenant fijado: RLS filtra todo lo que toca."""

    def __init__(self, engine: Engine, tenant_id: UUID, cifrador: Cifrador):
        self._engine = engine
        self._tenant_id = tenant_id
        self._cifrador = cifrador

    def crear_busqueda(self, criterios: CriteriosICP) -> UUID:
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            return c.execute(
                text("INSERT INTO busquedas (tenant_id, pais, criterios) VALUES (:t, :pais, CAST(:criterios AS jsonb)) "
                     "RETURNING id"),
                {"t": self._tenant_id, "pais": criterios.pais, "criterios": json.dumps(dict(criterios.filtros))},
            ).scalar_one()

    def obtener_o_crear_lead(self, e: EmpresaCruda, licencia: str) -> tuple[UUID, bool]:
        # ponytail: id_fiscal NULL (OSM) no choca con el UNIQUE, así que siempre crea lead nuevo; dedup difuso en Pulido.
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            nuevo = c.execute(_INSERT_LEAD, {
                "t": self._tenant_id, "pais": e.pais, "id_fiscal": e.id_fiscal, "nombre": e.nombre,
                "tipo_titular": e.tipo_titular, "ciudad": e.ciudad, "direccion": e.direccion,
                "codigo": e.actividad.codigo, "sistema": e.actividad.sistema, "web": e.web,
            }).scalar_one_or_none()
            if nuevo is None:
                existente = c.execute(
                    text("SELECT id FROM leads WHERE pais = :pais AND id_fiscal = :id_fiscal"),
                    {"pais": e.pais, "id_fiscal": e.id_fiscal},
                ).scalar_one()
                return existente, False
            c.execute(_INSERT_CUMPLIMIENTO, {
                "t": self._tenant_id, "lead_id": nuevo, "fuente": e.fuente, "licencia": licencia,
                "url_origen": e.url_origen, "as_of": e.as_of,
            })
            return nuevo, True

    def agregar_lead_fuente(self, lead_id: UUID, busqueda_id: UUID, e: EmpresaCruda, licencia: str) -> None:
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            c.execute(
                text("INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                     "VALUES (:t, :lead_id, :busqueda_id, :fuente, :url_origen, :licencia) "
                     "ON CONFLICT (lead_id, fuente, busqueda_id) DO NOTHING"),
                {"t": self._tenant_id, "lead_id": lead_id, "busqueda_id": busqueda_id, "fuente": e.fuente,
                 "url_origen": e.url_origen, "licencia": licencia},
            )

    def obtener_lead(self, lead_id: UUID) -> Lead | None:
        return None

    def cerrar_busqueda(self, busqueda_id: UUID, estado: str) -> None:
        with unidad_de_trabajo(self._engine, self._tenant_id) as c:
            c.execute(text("UPDATE busquedas SET estado = :estado WHERE id = :id"), {"estado": estado, "id": busqueda_id})
