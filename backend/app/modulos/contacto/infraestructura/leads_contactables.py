"""Leads de una búsqueda con email publicado (columnas de la 0008), descifrados solo para mandar."""
from uuid import UUID

from sqlalchemy import Engine, text

from app.db import unidad_de_trabajo
from app.modulos.contacto.dominio.modelos import LeadContactable
from app.seguridad.cifrado import Cifrador

# La elegibilidad legal se reevalúa en el repositorio al crear y al reclamar; acá solo se filtra lo que no tiene canal.
_SQL = ("SELECT DISTINCT l.id, l.email_cifrado, l.email_canal FROM leads l "
        "JOIN lead_fuentes lf ON lf.lead_id = l.id AND lf.busqueda_id = :b "
        "JOIN cumplimiento cu ON cu.lead_id = l.id AND cu.tenant_id = l.tenant_id "
        "WHERE l.tipo_titular = 'juridica' AND l.contactable AND l.email_cifrado IS NOT NULL AND cu.opt_out_at IS NULL "
        "ORDER BY l.id")


class LeadsContactablesPostgres:
    def __init__(self, engine: Engine, tenant_id: UUID, cifrador: Cifrador):
        self._engine, self._tenant, self._cifrador = engine, tenant_id, cifrador

    def de_busqueda(self, busqueda_id: UUID, canal: str) -> list[LeadContactable]:
        if canal != "email":
            return []
        with unidad_de_trabajo(self._engine, self._tenant) as c:
            filas = c.execute(text(_SQL), {"b": busqueda_id}).all()
        return [LeadContactable(lead, origen, self._cifrador.descifrar("email_cifrado", bytes(blob), self._tenant, lead))
                for lead, blob, origen in filas]
