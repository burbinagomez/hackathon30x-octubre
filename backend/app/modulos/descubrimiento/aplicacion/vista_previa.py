from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.dominio.puertos import FabricaFuentes, RepositorioLeads


@dataclass(frozen=True)
class FuenteVistaPrevia:
    clave: str
    ignorados: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoVistaPrevia:
    busqueda_id: UUID | None = None
    fuentes: tuple[FuenteVistaPrevia, ...] = ()
    descartadas: Mapping[str, str] = field(default_factory=dict)  # clave -> motivo (código, nunca frase)


class VistaPrevia:
    def __init__(self, repo: RepositorioLeads, fabrica: FabricaFuentes, actividades: Mapping[str, tuple[str, ...]]):
        self._repo = repo
        self._fabrica = fabrica
        self._actividades = actividades

    def ejecutar(self, criterios: CriteriosICP, canal_preferido: str | None, tope_gasto_usd,
                 mensaje_base: str | None) -> ResultadoVistaPrevia:
        return ResultadoVistaPrevia()  # esqueleto T004
