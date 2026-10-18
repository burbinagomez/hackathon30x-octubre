from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from uuid import UUID

from app.modulos.descubrimiento.dominio.errores import (
    BusquedaNoEncontrada,
    BusquedaYaEjecutada,
    FuenteNoDisponible,
    LimiteFuenteAgotado,
)
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


def _correr_fuentes(
    repo: RepositorioLeads,
    busqueda_id: UUID,
    criterios: CriteriosICP,
    metas: Mapping[str, MetaFuente],
    armar: Callable[[str], FuenteDescubrimiento],
    actividades: Mapping[str, tuple[str, ...]],
    estado_sin_fuente: str,
    estado_final: Callable[[Mapping[str, Exception], int], str],
) -> ResultadoBusqueda:
    """El núcleo de las dos entradas (CLI y API): selección, llamadas, dedup por NIT, lead_fuentes y estado final.
    `armar(clave)` entrega la fuente ya atada al lote = busqueda_id; `estado_final(errores, n_seleccionadas)`."""
    seleccionadas, _ = seleccionar_fuentes(list(metas.values()), criterios, actividades)
    if not seleccionadas:
        repo.cerrar_busqueda(busqueda_id, estado_sin_fuente)
        return ResultadoBusqueda(busqueda_id, sin_fuente_para=(criterios.pais, criterios.filtros))

    errores: dict[str, Exception] = {}
    encontrados, nuevos, leads = 0, 0, set()
    for clave, criterios_fuente in seleccionadas.items():
        meta = metas[clave]
        try:
            # ponytail: solo página 1; paginar cuando una fuente real devuelva más de una.
            pagina = armar(clave).buscar(criterios_fuente, 1)
        except (LimiteFuenteAgotado, FuenteNoDisponible) as error:
            errores[clave] = error
            continue
        for empresa in pagina.empresas:
            if empresa.id_fiscal is not None:
                empresa = replace(empresa, id_fiscal=normalizar_nit(empresa.id_fiscal))
            lead_id, nuevo = repo.obtener_o_crear_lead(empresa, meta.licencia)
            encontrados += 1
            nuevos += nuevo
            leads.add(lead_id)
            repo.agregar_lead_fuente(lead_id, busqueda_id, empresa, meta.licencia)

    repo.cerrar_busqueda(busqueda_id, estado_final(errores, len(seleccionadas)))
    return ResultadoBusqueda(busqueda_id, errores=errores, encontrados=encontrados, unicos=len(leads), nuevos=nuevos)


class EjecutarBusqueda:
    """Entrada de la CLI (002/003): crea la búsqueda con los criterios que recibe y la corre."""

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
        return _correr_fuentes(
            self._repo, busqueda_id, criterios,
            metas={clave: meta for clave, (meta, _) in self._fuentes.items()},
            # lote_id = busqueda_id: el CPL de la 005 agrupa los costos por búsqueda.
            armar=lambda clave: self._fuentes[clave][1](busqueda_id),
            actividades=self._actividades,
            estado_sin_fuente="terminada",
            estado_final=lambda errores, _: "con_errores" if errores else "terminada",
        )


def _estado_api(errores: Mapping[str, Exception], seleccionadas: int) -> str:
    """P1: una fuente caída con otra que respondió deja `completada` (el error viaja por fuente); `error`, solo si fallaron todas."""
    return "error" if len(errores) == seleccionadas else "completada"


class EjecutarBorrador:
    """Entrada de la API: corre un borrador guardado, con sus criterios congelados y lote_id = busqueda_id."""

    def __init__(self, repo: RepositorioLeads, fabrica: FabricaFuentes, actividades: Mapping[str, tuple[str, ...]]):
        self._repo = repo
        self._fabrica = fabrica
        self._actividades = actividades

    def ejecutar(self, busqueda_id: UUID) -> ResultadoBusqueda:
        estado = self._repo.estado(busqueda_id)
        if estado is None:  # no existe o es de otro tenant: RLS no deja distinguirlo, y no hay que distinguirlo
            raise BusquedaNoEncontrada
        borrador = self._repo.obtener_borrador(busqueda_id) if estado == "borrador" else None
        # El bool es lo que cierra la carrera: dos peticiones pueden leer `borrador`, solo una hace la transición.
        if borrador is None or not self._repo.pasar_a_ejecutando(busqueda_id):
            raise BusquedaYaEjecutada
        try:
            fuentes = self._fabrica(busqueda_id)
            return _correr_fuentes(
                self._repo, busqueda_id, borrador.criterios,
                metas={clave: f.meta for clave, f in fuentes.items()},
                armar=fuentes.__getitem__,
                actividades=self._actividades,
                estado_sin_fuente="completada",
                estado_final=_estado_api,
            )
        except Exception:
            self._repo.cerrar_busqueda(busqueda_id, "error")  # nunca queda `ejecutando` para siempre
            raise
