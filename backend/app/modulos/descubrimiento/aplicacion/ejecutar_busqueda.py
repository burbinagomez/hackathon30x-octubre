from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from uuid import UUID

from app.modulos.descubrimiento.dominio.errores import FuenteNoDisponible, LimiteFuenteAgotado
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente
from app.modulos.descubrimiento.dominio.nit import normalizar_nit
from app.modulos.descubrimiento.dominio.puertos import FabricaFuentes, FuenteDescubrimiento, RepositorioLeads
from app.modulos.descubrimiento.dominio.seleccion import seleccionar_fuentes

FabricaFuente = Callable[[UUID], FuenteDescubrimiento]  # lote_id -> fuente armada para esa búsqueda


@dataclass(frozen=True)
class ResultadoBusqueda:
    busqueda_id: UUID
    sin_fuente_para: tuple[str, Mapping] | None = None  # (pais, filtros) si ninguna fuente cubre el ICP
    errores: Mapping[str, Exception] = field(default_factory=dict)  # clave de fuente -> error, sin tragar
    encontrados: int = 0  # empresas devueltas por las fuentes
    unicos: int = 0  # leads distintos entre ellas
    nuevos: int = 0  # leads creados en esta búsqueda


class EjecutarBusqueda:
    def __init__(
        self,
        repo: RepositorioLeads,
        fuentes: Mapping[str, tuple[MetaFuente, FabricaFuente]],
        actividades: Mapping[str, tuple[str, ...]],
    ):
        self._repo = repo
        self._fuentes = fuentes
        self._actividades = actividades

    def ejecutar(self, criterios: CriteriosICP) -> ResultadoBusqueda:
        busqueda_id = self._repo.crear_busqueda(criterios)
        seleccionadas, _ = seleccionar_fuentes([m for m, _ in self._fuentes.values()], criterios, self._actividades)
        if not seleccionadas:
            self._repo.cerrar_busqueda(busqueda_id, "terminada")
            return ResultadoBusqueda(busqueda_id, sin_fuente_para=(criterios.pais, criterios.filtros))

        errores: dict[str, Exception] = {}
        encontrados, nuevos, leads = 0, 0, set()
        for clave, criterios_fuente in seleccionadas.items():
            meta, fabrica = self._fuentes[clave]
            try:
                # lote_id = busqueda_id: el CPL de la 005 agrupa los costos por búsqueda.
                # ponytail: solo página 1; paginar cuando una fuente real devuelva más de una.
                pagina = fabrica(busqueda_id).buscar(criterios_fuente, 1)
            except (LimiteFuenteAgotado, FuenteNoDisponible) as error:
                errores[clave] = error
                continue
            for empresa in pagina.empresas:
                if empresa.id_fiscal is not None:
                    empresa = replace(empresa, id_fiscal=normalizar_nit(empresa.id_fiscal))
                lead_id, nuevo = self._repo.obtener_o_crear_lead(empresa, meta.licencia)
                encontrados += 1
                nuevos += nuevo
                leads.add(lead_id)
                self._repo.agregar_lead_fuente(lead_id, busqueda_id, empresa, meta.licencia)

        self._repo.cerrar_busqueda(busqueda_id, "con_errores" if errores else "terminada")
        return ResultadoBusqueda(busqueda_id, errores=errores, encontrados=encontrados, unicos=len(leads), nuevos=nuevos)


class EjecutarBorrador:
    """Entrada de la API: corre un borrador guardado, con sus criterios congelados y lote_id = busqueda_id."""

    def __init__(self, repo: RepositorioLeads, fabrica: FabricaFuentes, actividades: Mapping[str, tuple[str, ...]]):
        self._repo = repo
        self._fabrica = fabrica
        self._actividades = actividades

    def ejecutar(self, busqueda_id: UUID) -> ResultadoBusqueda:
        return ResultadoBusqueda(busqueda_id)  # esqueleto T026
