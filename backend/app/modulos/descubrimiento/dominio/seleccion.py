from collections.abc import Iterable, Mapping

from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente


def seleccionar_fuentes(
    metas: Iterable[MetaFuente],
    criterios: CriteriosICP,
    actividades: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, CriteriosICP], dict[str, str]]:
    return {}, {}
