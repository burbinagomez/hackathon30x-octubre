from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from app.modulos.descubrimiento.dominio.modelos import (
    CriteriosICP, EmpresaCruda, Lead, LeadParaEnriquecer, MetaFuente, PaginaEmpresas, ResultadoEnriquecimiento)


class FuenteDescubrimiento(Protocol):
    meta: MetaFuente

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas: ...


class RepositorioLeads(Protocol):
    def crear_busqueda(self, criterios: CriteriosICP) -> UUID:
        """Transacción propia, confirmada antes de llamar a los adaptadores."""
        ...

    def obtener_o_crear_lead(self, e: EmpresaCruda, licencia: str) -> tuple[UUID, bool]:
        """(id, nuevo). Si es nuevo, inserta lead + cumplimiento en una transacción."""
        ...

    def agregar_lead_fuente(self, lead_id: UUID, busqueda_id: UUID, e: EmpresaCruda, licencia: str) -> None:
        """ON CONFLICT DO NOTHING."""
        ...

    def cerrar_busqueda(self, busqueda_id: UUID, estado: str) -> None: ...

    def obtener_lead(self, lead_id: UUID) -> Lead | None:
        """Con nombre y dirección descifrados. None si no existe o es de otro tenant."""
        ...

    def sin_enriquecer(self, busqueda_id: UUID) -> list[LeadParaEnriquecer]:
        """Leads de la búsqueda con enriquecido_en NULL, descifrados."""
        ...

    def guardar_enriquecimiento(self, lead_id: UUID, r: ResultadoEnriquecimiento) -> None:
        """Una UPDATE. Contacto siempre cifrado; si sube a jurídica, nombre y dirección pasan a claro y se anota en cumplimiento."""
        ...


class FabricaFuentes(Protocol):
    """Arma las fuentes de UNA búsqueda: el lote_id nace en el caso de uso (lote = búsqueda). La implementa app/api."""

    def __call__(self, lote_id: UUID) -> Mapping[str, FuenteDescubrimiento]: ...
