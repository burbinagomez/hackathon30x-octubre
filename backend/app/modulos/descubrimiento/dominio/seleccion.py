from collections.abc import Iterable, Mapping

from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente

GEOGRAFIA = ("departamento", "ciudad")


def seleccionar_fuentes(
    metas: Iterable[MetaFuente],
    criterios: CriteriosICP,
    actividades: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, CriteriosICP], dict[str, str]]:
    """Por fuente: los criterios que declara (ciiu traducido a tipo_negocio si hace falta) o el motivo de ignorarla."""
    seleccionadas: dict[str, CriteriosICP] = {}
    ignoradas: dict[str, str] = {}
    for meta in metas:
        # Solo el país: T016b deja `cubre()` así y entonces se usa acá.
        if criterios.pais not in meta.paises and "*" not in meta.paises:
            ignoradas[meta.clave] = "pais"
            continue

        filtros = {k: v for k, v in criterios.filtros.items() if k in meta.filtros}
        ciiu = criterios.filtros.get("ciiu")
        if ciiu is not None and "ciiu" not in meta.filtros and "tipo_negocio" in meta.filtros:
            etiquetas = actividades.get(str(ciiu))
            if not etiquetas:
                ignoradas[meta.clave] = "sin_mapeo_actividad"
                continue
            filtros["tipo_negocio"] = tuple(etiquetas)

        if not any(g in criterios.filtros and g in meta.filtros for g in GEOGRAFIA):
            ignoradas[meta.clave] = "sin_geografia"
            continue

        seleccionadas[meta.clave] = CriteriosICP(criterios.pais, filtros)
    return seleccionadas, ignoradas
