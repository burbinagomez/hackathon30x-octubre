from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.dominio.puertos import FabricaFuentes, RepositorioLeads
from app.modulos.descubrimiento.dominio.seleccion import seleccionar_fuentes


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
        # Lote = búsqueda: el borrador se confirma primero y las fuentes se arman con su id.
        busqueda_id = self._repo.crear_borrador(criterios, canal_preferido, tope_gasto_usd, mensaje_base)
        fuentes = self._fabrica(busqueda_id)  # en el [MIN] solo se lee `.meta`; sin contar no hay operación de salida
        seleccionadas, descartadas = seleccionar_fuentes([f.meta for f in fuentes.values()], criterios, self._actividades)
        return ResultadoVistaPrevia(
            busqueda_id=busqueda_id,
            fuentes=tuple(FuenteVistaPrevia(clave, _ignorados(criterios, aplicados))
                          for clave, aplicados in seleccionadas.items()),
            descartadas=descartadas,
        )


def _ignorados(pedidos: CriteriosICP, aplicados: CriteriosICP) -> tuple[str, ...]:
    """Lo que el usuario pidió y la fuente no aplica. El ciiu que se tradujo a tipo_negocio sí se aplica (P7 corregido)."""
    traducido = {"ciiu"} if "tipo_negocio" in aplicados.filtros and "ciiu" not in aplicados.filtros else set()
    return tuple(sorted(set(pedidos.filtros) - set(aplicados.filtros) - traducido))
