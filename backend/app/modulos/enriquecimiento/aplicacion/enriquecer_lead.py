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
    sin_clasificar: int  # encaje NULL: no jurídica, sin ICP, jev apagado o jev falló; candidatos a reclasificar
    cortado: bool
    pendientes: int = 0  # los que quedaron sin enriquecer por el límite de la tanda (o por el corte)


class EnriquecerLead:
    """Por lead: todo el HTTP en memoria primero, después una UoW en el repo. El costo lo escribe cada adaptador."""

    def __init__(self, repo: RepositorioLeads, verificador: VerificadorTitular, enriquecedor: EnriquecedorContacto,
                 clasificador: ClasificadorEncaje | None):
        self._repo = repo
        self._verificador = verificador
        self._enriquecedor = enriquecedor
        self._clasificador = clasificador

    def ejecutar(self, busqueda_id: UUID, limite: int | None = None) -> ResumenEnriquecimiento:
        """`limite`: cuántos leads como máximo en esta corrida (la API corre por tandas); None = todos."""
        leads = self._repo.sin_enriquecer(busqueda_id)
        tanda = leads if limite is None else leads[:limite]
        procesados = contactables = clasificados = 0
        for lead in tanda:
            try:
                r = self._enriquecer(lead)
            except LimiteFuenteAgotado:  # recurso de la cuenta: seguir solo gastaría en el resto
                return ResumenEnriquecimiento(procesados, contactables, clasificados, procesados - clasificados, True,
                                              len(leads) - procesados)
            self._repo.guardar_enriquecimiento(lead.id, r)
            procesados += 1
            contactables += r.contactable
            clasificados += r.encaje is not None
        return ResumenEnriquecimiento(procesados, contactables, clasificados, procesados - clasificados, False,
                                      len(leads) - procesados)

    def _enriquecer(self, lead: LeadParaEnriquecer) -> ResultadoEnriquecimiento:
        tipo = lead.tipo_titular
        constancia = None
        if tipo == "desconocido":
            v = self._verificador.verificar(lead.id, lead.nombre, lead.ciudad)
            log.info("verificador_titular: %s", v.motivo)  # solo el motivo: nunca el nombre del lead
            tipo, constancia = v.tipo_titular, v.constancia  # la evidencia va a `cumplimiento`, no al lead
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
                                        self._clasificar(lead, tipo), constancia)

    def _clasificar(self, lead: LeadParaEnriquecer, tipo: str) -> str | None:
        # §2.5: solo jurídicas. Natural o desconocido no es contactable y su nombre puede ser el de una persona.
        if tipo != "juridica" or lead.descripcion_icp is None or self._clasificador is None:
            return None
        try:
            return self._clasificador.clasificar(
                lead.id, lead.descripcion_icp, lead.nombre, lead.ciudad, lead.actividad).etiqueta
        except (JevNoDisponible, SalidaJevInvalida, UsoJevInvalido) as e:
            # Cuenta solo contra este lead: queda sin clasificar y la corrida sigue. Solo la clase, nunca el lead.
            log.warning("jev no clasificó: %s", type(e).__name__)
            return None
