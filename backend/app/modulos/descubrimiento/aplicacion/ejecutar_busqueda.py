from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from uuid import UUID

from app.modulos.descubrimiento.dominio.errores import FuenteNoDisponible, LimiteFuenteAgotado
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente, cubre
from app.modulos.descubrimiento.dominio.nit import normalizar_nit
from app.modulos.descubrimiento.dominio.puertos import FuenteDescubrimiento, RepositorioLeads

FabricaFuente = Callable[[UUID], FuenteDescubrimiento]  # lote_id -> fuente armada para esa búsqueda


@dataclass(frozen=True)
class ResultadoBusqueda:
    busqueda_id: UUID
    sin_fuente_para: tuple[str, Mapping] | None = None  # (pais, filtros) si ninguna fuente cubre el ICP
    errores: Mapping[str, Exception] = field(default_factory=dict)  # clave de fuente -> error, sin tragar


class EjecutarBusqueda:
    def __init__(self, repo: RepositorioLeads, fuentes: Mapping[str, tuple[MetaFuente, FabricaFuente]]):
        self._repo = repo
        self._fuentes = fuentes

    def ejecutar(self, criterios: CriteriosICP) -> ResultadoBusqueda:
        busqueda_id = self._repo.crear_busqueda(criterios)
        cubren = {clave: par for clave, par in self._fuentes.items() if cubre(par[0], criterios)}
        if not cubren:
            self._repo.cerrar_busqueda(busqueda_id, "terminada")
            return ResultadoBusqueda(busqueda_id, sin_fuente_para=(criterios.pais, criterios.filtros))

        errores: dict[str, Exception] = {}
        for clave, (meta, fabrica) in cubren.items():
            try:
                # lote_id = busqueda_id: el CPL de la 005 agrupa los costos por búsqueda.
                # ponytail: solo página 1; paginar cuando una fuente real devuelva más de una.
                pagina = fabrica(busqueda_id).buscar(criterios, 1)
            except (LimiteFuenteAgotado, FuenteNoDisponible) as error:
                errores[clave] = error
                continue
            for empresa in pagina.empresas:
                if empresa.id_fiscal is not None:
                    empresa = replace(empresa, id_fiscal=normalizar_nit(empresa.id_fiscal))
                lead_id, _ = self._repo.obtener_o_crear_lead(empresa, meta.licencia)
                self._repo.agregar_lead_fuente(lead_id, busqueda_id, empresa, meta.licencia)

        self._repo.cerrar_busqueda(busqueda_id, "con_errores" if errores else "terminada")
        return ResultadoBusqueda(busqueda_id, errores=errores)
