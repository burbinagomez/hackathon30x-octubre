"""Puerta A: de una lista de nombres a una sugerencia de filtros. No escribe costos, no persiste los nombres."""
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.modulos.costos.dominio.modelos import ContextoCosto
from app.modulos.intake.dominio.agregar_distribucion import Distribucion, agregar_distribucion
from app.modulos.intake.dominio.errores import IntakeFueraDeRango
from app.modulos.intake.dominio.normalizar import normalizar_nombre
from app.modulos.intake.dominio.puertos_lookalike import BuscadorRazonSocial

MINIMO, MAXIMO = 5, 50
FUENTE_COSTO = "intake"


@dataclass(frozen=True)
class ResultadoLookalike:
    distribucion: Distribucion
    resueltos: int
    no_resueltos: list[str]  # como los pegó el usuario; vuelven a su pantalla, no se guardan
    lote_id: UUID


class ResolverLookalike:
    def __init__(
        self,
        buscador: BuscadorRazonSocial,
        camara_a_departamento: Mapping[str, str],
        ciiu_validos: Collection[str] | None = None,
        nuevo_lote: Callable[[], UUID] = uuid4,
    ) -> None:
        self._buscador = buscador
        self._camaras = camara_a_departamento
        self._ciiu_validos = ciiu_validos
        self._nuevo_lote = nuevo_lote

    def ejecutar(self, nombres: Sequence[str]) -> ResultadoLookalike:
        pegados = [n.strip() for n in nombres if n.strip()]
        if not MINIMO <= len(pegados) <= MAXIMO:
            raise IntakeFueraDeRango
        # Un nombre escrito dos veces se consulta una sola: cada consulta es un request.
        unicos: dict[str, str] = {}
        no_resueltos: list[str] = []
        for crudo in pegados:
            clave = normalizar_nombre(crudo)
            if not clave:
                no_resueltos.append(crudo)
            elif clave not in unicos:
                unicos[clave] = crudo
        contexto = ContextoCosto(FUENTE_COSTO, self._nuevo_lote())
        matches, resueltos = [], 0
        for clave, crudo in unicos.items():
            coincidencias = list(self._buscador.buscar_coincidencias(clave, contexto))
            if len({c.nit for c in coincidencias}) == 1:  # 0 o 2+ NIT distintos: no resuelve
                matches.extend(coincidencias[:1])
                resueltos += 1
            else:
                no_resueltos.append(crudo)
        # El orden de los no resueltos sigue al de la lista pegada.
        orden = {n: i for i, n in enumerate(pegados)}
        no_resueltos.sort(key=lambda n: orden[n])
        distribucion = agregar_distribucion(matches, self._camaras, self._ciiu_validos)
        return ResultadoLookalike(distribucion, resueltos, no_resueltos, contexto.lote_id)
