from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from app.modulos.costos.dominio.modelos import ContextoCosto
from app.modulos.descubrimiento.dominio.modelos import ConstanciaTitular, EvidenciaSitioWeb
from app.modulos.enriquecimiento.dominio.canal import CanalPublicado


@dataclass(frozen=True)
class ContactoPublicado:
    emails: tuple[str, ...]
    telefonos: tuple[tuple[str, CanalPublicado], ...]  # (valor, canal); el valor nunca sale de memoria sin cifrar
    estado: Literal["ok", "sin_sitio", "fetch_bloqueado_por_robots", "truncado", "fallo"]


@dataclass(frozen=True)
class VerificacionTitular:
    tipo_titular: Literal["juridica", "desconocido"]
    motivo: Literal["match_unico", "sin_match", "ambiguo", "matricula_inactiva", "sin_ciudad", "fuente_no_disponible",
                     "pais_no_soportado"]
    constancia: ConstanciaTitular | None = None  # va a `cumplimiento`; el motivo, además, al log de la corrida


@dataclass(frozen=True)
class Encaje:
    etiqueta: Literal["encaja", "no_encaja", "ninguna"]
    probabilidad: float


class EnriquecedorContacto(Protocol):  # sitio_web
    def enriquecer(self, lead_id: UUID, dominio: str) -> ContactoPublicado: ...


class BuscadorSitioWeb(Protocol):  # dominio_por_razon_social
    def buscar(self, lead_id: UUID, razon_social: str, nit: str | None) -> EvidenciaSitioWeb | None:
        """El sitio de la empresa si se pudo VERIFICAR que es suyo (NIT o razón social en la página); si no, None.
        Quien lo cumple escribe el costo de cada request con `lead_id`, antes de devolver."""
        ...


class VerificadorTitular(Protocol):  # rues_datos_gov_co (real) o croma_rues_co (stub que siempre dice desconocido)
    def verificar(self, lead_id: UUID, nombre_normalizado: str, ciudad: str | None, pais: str) -> VerificacionTitular: ...


class ClasificadorEncaje(Protocol):  # jev
    def clasificar(self, lead_id: UUID, descripcion_icp: str, nombre: str, ciudad: str | None,
                   actividad: str | None) -> Encaje: ...


@runtime_checkable
class CoincidenciaRues(Protocol):
    @property
    def nit(self) -> str: ...
    @property
    def razon_social(self) -> str | None: ...
    @property
    def camara(self) -> str | None: ...
    @property
    def estado_matricula(self) -> str | None: ...
    @property
    def organizacion_juridica(self) -> str | None: ...


@runtime_checkable
class BusquedaRues(Protocol):
    @property
    def coincidencias(self) -> Sequence[CoincidenciaRues]: ...
    @property
    def truncada(self) -> bool: ...


@runtime_checkable
class BuscadorRazonSocialRues(Protocol):
    """Lo que `RuesDatosGov` pide a un cliente del RUES. El consumidor es dueño de su puerto: el cliente de
    datos.gov.co de la 011 lo cumple por estructura y solo la raíz de composición los une. Quien lo cumple escribe
    el costo de cada request con el `lead_id` del contexto, antes de devolver."""

    def buscar_homonimas(self, nombre_normalizado: str, contexto_costo: ContextoCosto) -> BusquedaRues:
        """Jurídicas cuya razón social contiene el nombre, y si el servidor cortó en su tope de filas."""
        ...

    def contar_naturales(self, nombre_normalizado: str, camaras: Collection[str], contexto_costo: ContextoCosto) -> int:
        """Personas naturales matriculadas con ese nombre en esas cámaras. Solo un conteo, nunca sus nombres."""
        ...
