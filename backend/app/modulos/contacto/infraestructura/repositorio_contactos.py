"""Contactos en Postgres. La elegibilidad legal vive en SQL y se reevalúa al crear, al reclamar y antes de mandar."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo

BASE_LEGAL = "persona_juridica_canal_publicado"

# Jurídica, con fila de cumplimiento y sin opt-out. {lead} es un parámetro o una columna.
_ELEGIBLE = ("EXISTS (SELECT 1 FROM leads l JOIN cumplimiento cu ON cu.lead_id = l.id AND cu.tenant_id = l.tenant_id "
             "WHERE l.id = {lead} AND l.tipo_titular = 'juridica' AND cu.opt_out_at IS NULL)")


class RepositorioContactosPostgres:
    def __init__(self, engine: Engine, tenant_id: UUID):
        self._engine, self._tenant = engine, tenant_id

    def _ejecutar(self, sql: str, leer=lambda r: r.rowcount, **params):
        with unidad_de_trabajo(self._engine, self._tenant) as c:
            return leer(c.execute(text(sql), params))

    def mensaje_base(self, busqueda_id: UUID) -> str | None:
        return self._ejecutar("SELECT mensaje_base FROM busquedas WHERE id = :b", lambda r: r.scalar(), b=busqueda_id)

    def aprobados(self, busqueda_id: UUID) -> list[tuple[UUID, UUID, str]]:
        return self._ejecutar(
            "SELECT id, lead_id, cuerpo FROM contactos WHERE busqueda_id = :b AND estado = 'aprobado' "
            "ORDER BY creado_en, id", lambda r: [tuple(f) for f in r.all()], b=busqueda_id)

    def crear(self, busqueda_id: UUID, contacto_id: UUID, lead_id: UUID, asunto: str, cuerpo: str) -> bool:
        return self._ejecutar(
            "INSERT INTO contactos (id, tenant_id, lead_id, busqueda_id, canal, asunto, cuerpo) "
            "SELECT :c, :t, :l, :b, 'email', :a, :cu WHERE " + _ELEGIBLE.format(lead=":l") + " ON CONFLICT DO NOTHING",
            c=contacto_id, t=self._tenant, l=lead_id, b=busqueda_id, a=asunto, cu=cuerpo) == 1

    def fijar_mensaje(self, contacto_id: UUID, asunto: str, cuerpo: str) -> None:
        self._ejecutar("UPDATE contactos SET asunto = :a, cuerpo = :cu WHERE id = :c AND estado = 'aprobado'",
                       c=contacto_id, a=asunto, cu=cuerpo)

    def reclamar(self, contacto_id: UUID) -> bool:
        with unidad_de_trabajo(self._engine, self._tenant) as c:
            lead = c.execute(text(
                "UPDATE contactos SET estado = 'enviando' WHERE id = :c AND estado = 'aprobado' AND "
                + _ELEGIBLE.format(lead="contactos.lead_id") + " RETURNING lead_id"), {"c": contacto_id}).scalar()
            if lead is None:
                return False
            c.execute(text("UPDATE cumplimiento SET base_legal = COALESCE(base_legal, :bl) WHERE lead_id = :l"), {"bl": BASE_LEGAL, "l": lead})
            return True

    def vigente(self, contacto_id: UUID) -> bool:
        return self._ejecutar(
            "SELECT EXISTS (SELECT 1 FROM contactos co JOIN cumplimiento cu "
            "ON cu.lead_id = co.lead_id AND cu.tenant_id = co.tenant_id "
            "WHERE co.id = :c AND co.estado = 'enviando' AND cu.base_legal IS NOT NULL AND "
            + _ELEGIBLE.format(lead="co.lead_id") + ")", lambda r: r.scalar(), c=contacto_id)

    def confirmar(self, contacto_id: UUID) -> None:
        self._ejecutar("UPDATE contactos SET estado = 'enviado', enviado_en = now() "
                       "WHERE id = :c AND estado = 'enviando'", c=contacto_id)

    def liberar(self, contacto_id: UUID) -> None:
        self._ejecutar("UPDATE contactos SET estado = 'aprobado' WHERE id = :c AND estado = 'enviando'", c=contacto_id)

    def descartar(self, contacto_id: UUID) -> None:
        self._ejecutar("UPDATE contactos SET estado = 'descartado' WHERE id = :c AND estado IN ('aprobado', 'enviando')",
                       c=contacto_id)

    def dar_de_baja(self, contacto_id: UUID, via: str) -> bool:
        with unidad_de_trabajo(self._engine, self._tenant) as c:
            lead = c.execute(text(
                "UPDATE cumplimiento SET opt_out_at = COALESCE(opt_out_at, now()), "
                # Solo la primera baja queda registrada: repetir el enlace no infla solicitudes.
                "solicitudes = CASE WHEN opt_out_at IS NULL THEN solicitudes || jsonb_build_array(jsonb_build_object("
                "'tipo', 'baja', 'via', CAST(:v AS text), 'ts', now())) ELSE solicitudes END "
                "WHERE lead_id = (SELECT lead_id FROM contactos WHERE id = :c) RETURNING lead_id"),
                {"c": contacto_id, "v": via}).scalar()
            if lead is None:
                return False
            # Por lead, no por contacto: la baja cierra todos los contactos de ese lead.
            c.execute(text("UPDATE contactos SET bloqueo = true, estado = CASE WHEN estado IN "
                           "('aprobado', 'pendiente_aprobacion') THEN 'descartado' ELSE estado END WHERE lead_id = :l"),
                      {"l": lead})
            return True

    def marcar_respondio(self, contacto_id: UUID) -> bool:
        return self._ejecutar("UPDATE contactos SET respondio_en = COALESCE(respondio_en, now()) "
                              "WHERE id = :c AND enviado_en IS NOT NULL", c=contacto_id) == 1

    def de_busqueda(self, busqueda_id: UUID) -> list[tuple[UUID, str, object, object]]:
        """Los contactos de una búsqueda para la pantalla: id, estado y fechas. Ni dirección ni nombre del lead."""
        return self._ejecutar("SELECT id, estado, enviado_en, respondio_en FROM contactos WHERE busqueda_id = :b "
                              "ORDER BY creado_en, id", leer=lambda r: [tuple(f) for f in r.all()], b=busqueda_id)

    def tasa_por_canal(self) -> list[tuple[str, int, int, Decimal | None]]:
        return self._ejecutar("SELECT canal, contactados, respondieron, tasa FROM v_tasa_respuesta_canal ORDER BY canal",
                              lambda r: [tuple(f) for f in r.all()])
