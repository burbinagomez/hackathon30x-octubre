import logging
from dataclasses import dataclass
from uuid import UUID

from app.modulos.descubrimiento.dominio.errores import LimiteFuenteAgotado
from app.modulos.descubrimiento.dominio.modelos import LeadParaEnriquecer, ResultadoEnriquecimiento
from app.modulos.descubrimiento.dominio.puertos import RepositorioLeads
from app.modulos.enriquecimiento.dominio.canal import elegir_canal
from app.modulos.enriquecimiento.dominio.contactable import calcular_contactable, es_contacto_nominal
from app.modulos.enriquecimiento.dominio.errores import JevNoDisponible, SalidaJevInvalida, UsoJevInvalido
from app.modulos.enriquecimiento.dominio.puertos import ClasificadorEncaje, EnriquecedorContacto, VerificadorTitular

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResumenEnriquecimiento:
    """Lo único que sale de la corrida: conteos, nunca contacto."""
    procesados: int
    contactables: int
    clasificados: int
    sin_clasificar: int  # encaje NULL: sin ICP, jev apagado o jev falló; candidatos a reclasificar
    cortado: bool


class EnriquecerLead:
    """Por lead: todo el HTTP en memoria primero, después una UoW en el repo. El costo lo escribe cada adaptador."""

    def __init__(self, repo: RepositorioLeads, verificador: VerificadorTitular, enriquecedor: EnriquecedorContacto,
                 clasificador: ClasificadorEncaje | None):
        self._repo = repo
        self._verificador = verificador
        self._enriquecedor = enriquecedor
        self._clasificador = clasificador

    def ejecutar(self, busqueda_id: UUID) -> ResumenEnriquecimiento:
        procesados = contactables = clasificados = 0
        for lead in self._repo.sin_enriquecer(busqueda_id):
            try:
                r = self._enriquecer(lead)
            except LimiteFuenteAgotado:  # recurso de la cuenta: seguir solo gastaría en el resto
                return ResumenEnriquecimiento(procesados, contactables, clasificados, procesados - clasificados, True)
            self._repo.guardar_enriquecimiento(lead.id, r)
            procesados += 1
            contactables += r.contactable
            clasificados += r.encaje is not None
        return ResumenEnriquecimiento(procesados, contactables, clasificados, procesados - clasificados, False)

    def _enriquecer(self, lead: LeadParaEnriquecer) -> ResultadoEnriquecimiento:
        tipo = lead.tipo_titular
        if tipo == "desconocido":
            v = self._verificador.verificar(lead.id, lead.nombre, lead.ciudad)
            log.info("croma_rues_co: %s", v.motivo)  # la razón va al log de la corrida, no al lead
            tipo = v.tipo_titular
        telefono, email = lead.telefono, lead.email
        if lead.web:
            c = self._enriquecedor.enriquecer(lead.id, lead.web)
            for t in c.telefonos:
                telefono = elegir_canal(telefono, t)
            if c.emails:  # uno de empresa antes que uno nominal
                email = elegir_canal(email, (min(c.emails, key=es_contacto_nominal), "sitio_web"))
        nominal = email is not None and es_contacto_nominal(email[0])
        contactable, razon = calcular_contactable(tipo, telefono and telefono[1], email and email[1], nominal)
        return ResultadoEnriquecimiento(tipo, telefono, None if nominal else email, contactable, razon,
                                        self._clasificar(lead))

    def _clasificar(self, lead: LeadParaEnriquecer) -> str | None:
        if lead.descripcion_icp is None or self._clasificador is None:
            return None
        try:
            return self._clasificador.clasificar(
                lead.id, lead.descripcion_icp, lead.nombre, lead.ciudad, lead.actividad).etiqueta
        except (JevNoDisponible, SalidaJevInvalida, UsoJevInvalido) as e:
            # Cuenta solo contra este lead: queda sin clasificar y la corrida sigue. Solo la clase, nunca el lead.
            log.warning("jev no clasificó: %s", type(e).__name__)
            return None
