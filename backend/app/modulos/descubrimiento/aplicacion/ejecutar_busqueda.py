from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from uuid import UUID

from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente
from app.modulos.descubrimiento.dominio.puertos import FuenteDescubrimiento, RepositorioLeads

FabricaFuente = Callable[[UUID], FuenteDescubrimiento]  # lote_id -> fuente armada para esa búsqueda


@dataclass(frozen=True)
class ResultadoBusqueda:
    busqueda_id: UUID | None
    sin_fuente_para: tuple[str, Mapping] | None = None  # (pais, filtros) si ninguna fuente cubre el ICP
    errores: Mapping[str, Exception] = field(default_factory=dict)  # clave de fuente -> error, sin tragar


class EjecutarBusqueda:
    """Esqueleto de T038: el Verde es T039."""

    def __init__(self, repo: RepositorioLeads, fuentes: Mapping[str, tuple[MetaFuente, FabricaFuente]]):
        self._repo = repo
        self._fuentes = fuentes

    def ejecutar(self, criterios: CriteriosICP) -> ResultadoBusqueda:
        return ResultadoBusqueda(busqueda_id=None)
