import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from uuid import UUID

from app.modulos.descubrimiento.dominio.errores import LimiteFuenteAgotado
from app.modulos.descubrimiento.dominio.modelos import LeadParaEnriquecer, ResultadoEnriquecimiento
from app.modulos.descubrimiento.dominio.puertos import RepositorioLeads
from app.modulos.enriquecimiento.dominio.canal import elegir_canal
from app.modulos.enriquecimiento.dominio.contactable import calcular_contactable, es_contacto_nominal
from app.modulos.enriquecimiento.dominio.errores import JevNoDisponible, SalidaJevInvalida, UsoJevInvalido
from app.modulos.enriquecimiento.dominio.puertos import (
    BuscadorSitioWeb,
    ClasificadorEncaje,
    EnriquecedorContacto,
    VerificadorTitular,
)

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
                 clasificador: ClasificadorEncaje | None, buscador: BuscadorSitioWeb | None = None,
                 max_hilos: int = 1, reloj: Callable[[], float] = time.monotonic):
        self._repo = repo
        self._verificador = verificador
        self._enriquecedor = enriquecedor
        self._clasificador = clasificador
        self._buscador = buscador  # None = apagado por config: un lead sin web se queda sin web
        self._max_hilos = max(1, max_hilos)
        self._reloj = reloj

    def ejecutar(self, busqueda_id: UUID, limite: int | None = None, presupuesto_s: float | None = None) -> ResumenEnriquecimiento:
        """`limite`: cuántos leads como máximo en esta corrida (la API corre por tandas); None = todos.
        `presupuesto_s`: tiempo total de la tanda; los leads que no terminaron quedan pendientes (no se guardan) para la
        próxima. Los leads de la tanda se enriquecen en paralelo (`max_hilos`); lo único que escribe el repo es este hilo."""
        leads = self._repo.sin_enriquecer(busqueda_id)
        tanda = leads if limite is None else leads[:limite]
        limite_t = None if presupuesto_s is None else self._reloj() + presupuesto_s
        agotado = threading.Event()  # un LimiteFuenteAgotado frena a los que todavía no arrancaron

        def tarea(lead: LeadParaEnriquecer) -> ResultadoEnriquecimiento | None:
            if agotado.is_set() or (limite_t is not None and self._reloj() >= limite_t):
                return None  # no arrancó: queda pendiente
            try:
                return self._enriquecer(lead)
            except LimiteFuenteAgotado:
                agotado.set()
                raise

        pool = ThreadPoolExecutor(max_workers=min(self._max_hilos, max(1, len(tanda))))
        try:
            futuros = [pool.submit(tarea, lead) for lead in tanda]
            wait(futuros, timeout=None if limite_t is None else max(0.0, limite_t - self._reloj()))
        finally:
            pool.shutdown(wait=False, cancel_futures=True)  # los hilos que siguen no guardan nada: el repo es de este hilo
        procesados = contactables = clasificados = 0
        for lead, futuro in zip(tanda, futuros, strict=True):
            if not futuro.done() or futuro.cancelled():
                continue
            try:
                r = futuro.result()
            except LimiteFuenteAgotado:  # recurso de la cuenta: seguir solo gastaría en el resto
                return ResumenEnriquecimiento(procesados, contactables, clasificados, procesados - clasificados, True,
                                              len(leads) - procesados)
            if r is None:
                continue
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
            v = self._verificador.verificar(lead.id, lead.nombre, lead.ciudad, lead.pais)
            log.info("verificador_titular: %s", v.motivo)  # solo el motivo: nunca el nombre del lead
            tipo, constancia = v.tipo_titular, v.constancia  # la evidencia va a `cumplimiento`, no al lead
        telefono, email = lead.telefono, lead.email
        web, evidencia = lead.web, None
        if not web and tipo == "juridica" and self._buscador is not None:
            # Solo se guarda un sitio verificado (NIT o razón social en su página); la evidencia va a `cumplimiento`.
            evidencia = self._buscador.buscar(lead.id, lead.nombre, lead.id_fiscal)
            web = evidencia.dominio if evidencia else None
        if web:
            c = self._enriquecedor.enriquecer(lead.id, web)
            for t in c.telefonos:
                telefono = elegir_canal(telefono, t)
            if c.emails:  # uno de empresa antes que uno nominal
                email = elegir_canal(email, (min(c.emails, key=es_contacto_nominal), "sitio_web"))
        nominal = email is not None and es_contacto_nominal(email[0])
        contactable, razon = calcular_contactable(tipo, telefono and telefono[1], email and email[1], nominal)
        return ResultadoEnriquecimiento(tipo, telefono, None if nominal else email, contactable, razon,
                                        self._clasificar(lead, tipo), constancia, evidencia.dominio if evidencia else None,
                                        evidencia)

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
