"""Envío a una búsqueda en dos pasos (P1): el --dry-run deja los contactos aprobados; enviar solo manda esos."""
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.modulos.contacto.dominio.errores import (CanalNoDisponible, DestinatarioInvalido, MensajeCambio,
                                                  PlantillaInvalida, SinVistaPrevia)
from app.modulos.contacto.dominio.modelos import LeadContactable, MensajeSaliente
from app.modulos.contacto.dominio.plantilla import componer, validar
from app.modulos.contacto.dominio.puertos import CanalContacto, LeadsContactables, RepositorioContactos
from app.modulos.contacto.dominio.tokens import firmar

TOPE_POR_CORRIDA = 20


@dataclass(frozen=True)
class Resumen:
    """Lo que imprime el dry-run. Sin direcciones."""
    aprobados: int
    a_enviar: int
    modo: str
    asunto: str | None
    cuerpo: str | None


class EnviarABusqueda:
    def __init__(self, tenant_id: UUID, repo: RepositorioContactos, leads: LeadsContactables, canal: CanalContacto,
                 clave_baja: bytes, remitente: str, url_api: str, url_privacidad: str, modo: str,
                 destinos_prueba: Sequence[str], tope: int = TOPE_POR_CORRIDA):
        self._tenant, self._repo, self._leads, self._canal = tenant_id, repo, leads, canal
        self._clave, self._remitente, self._url_privacidad = clave_baja, remitente, url_privacidad
        self._url_api = url_api.rstrip("/")
        self._modo, self._tope = modo, tope
        self._destinos = {d.casefold() for d in destinos_prueba}

    def _token_baja(self, contacto_id: UUID) -> str:
        return firmar(self._clave, "baja", self._tenant, contacto_id)

    def _componer(self, mensaje_base: str, contacto_id: UUID, lead: LeadContactable) -> tuple[str, str] | None:
        """El cuerpo es determinista por contacto: recomponer y comparar detecta un mensaje_base cambiado."""
        url_baja = f"{self._url_api}/baja/{self._token_baja(contacto_id)}"
        try:
            asunto, cuerpo = componer(mensaje_base, self._remitente, lead.canal_origen, url_baja, self._url_privacidad)
            validar(cuerpo, self._remitente, url_baja, self._url_privacidad)
        except PlantillaInvalida:
            return None
        return asunto, cuerpo

    def _de_busqueda(self, busqueda_id: UUID) -> dict[UUID, LeadContactable]:
        return {lead.lead_id: lead for lead in self._leads.de_busqueda(busqueda_id, self._canal.canal)}

    def _seleccion(self, filas: list) -> list:
        """Modo prueba (todo lo que no sea "real"): solo la lista de prueba, vacía = nada. Después, el tope."""
        if self._modo != "real":
            filas = [f for f in filas if f[1].direccion.casefold() in self._destinos]
        return filas[:self._tope]

    def vista_previa(self, busqueda_id: UUID, rehacer: bool = False) -> Resumen:
        base = self._repo.mensaje_base(busqueda_id) or ""
        leads = self._de_busqueda(busqueda_id)
        con_contacto = set()
        for cid, lead_id, cuerpo in self._repo.aprobados(busqueda_id):
            con_contacto.add(lead_id)
            if lead_id not in leads:
                continue
            nuevo = self._componer(base, cid, leads[lead_id])
            if nuevo is not None and nuevo[1] == cuerpo:
                continue
            if not rehacer:
                raise MensajeCambio()
            if nuevo is None:
                self._repo.descartar(cid)
            else:
                self._repo.fijar_mensaje(cid, *nuevo)
        for lead in leads.values():
            if lead.lead_id in con_contacto:
                continue
            cid = uuid4()
            if (nuevo := self._componer(base, cid, lead)) is not None:
                self._repo.crear(busqueda_id, cid, lead.lead_id, *nuevo)

        aprobados = self._repo.aprobados(busqueda_id)
        a_enviar = self._seleccion([(cid, leads[lid]) for cid, lid, _ in aprobados if lid in leads])
        # La muestra lleva un enlace de baja de ejemplo: el token real de cada contacto no se imprime.
        muestra = next(((leads[lid], cid) for cid, lid, _ in aprobados if lid in leads), None)
        asunto = cuerpo = None
        if muestra is not None:
            asunto, cuerpo = componer(base, self._remitente, muestra[0].canal_origen, f"{self._url_api}/baja/<token>",
                                      self._url_privacidad)
        return Resumen(len(aprobados), len(a_enviar), self._modo, asunto, cuerpo)

    def enviar(self, busqueda_id: UUID) -> int:
        aprobados = self._repo.aprobados(busqueda_id)
        if not aprobados:
            raise SinVistaPrevia()
        base = self._repo.mensaje_base(busqueda_id) or ""
        leads = self._de_busqueda(busqueda_id)
        filas = []
        for cid, lead_id, cuerpo in aprobados:
            if lead_id not in leads:
                continue
            nuevo = self._componer(base, cid, leads[lead_id])
            if nuevo is None or nuevo[1] != cuerpo:
                raise MensajeCambio()  # antes de mandar nada
            filas.append((cid, leads[lead_id], nuevo[0], cuerpo))

        enviados = 0
        for cid, lead, asunto, cuerpo in self._seleccion(filas):
            if not self._repo.reclamar(cid):
                continue  # otro envío lo reclamó, o dejó de ser elegible (opt-out, cumplimiento)
            if not self._repo.vigente(cid):
                self._repo.descartar(cid)
                continue
            mensaje = MensajeSaliente(cid, lead.lead_id, busqueda_id, asunto, cuerpo, self._token_baja(cid),
                                      firmar(self._clave, "msgid", self._tenant, cid), lead.direccion)
            try:
                self._canal.enviar(mensaje)
            except CanalNoDisponible:
                self._repo.liberar(cid)
                continue
            except DestinatarioInvalido:
                self._repo.descartar(cid)
                continue
            self._repo.confirmar(cid)
            enviados += 1
        return enviados
