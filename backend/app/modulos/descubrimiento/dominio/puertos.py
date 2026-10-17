from typing import Protocol
from uuid import UUID

from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, EmpresaCruda, MetaFuente, PaginaEmpresas


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
