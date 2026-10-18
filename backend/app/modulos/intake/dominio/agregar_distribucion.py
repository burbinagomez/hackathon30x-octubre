"""Moda de CIIU y de departamento sobre matches únicos por NIT. Puro: sin I/O ni framework."""
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from app.modulos.intake.dominio.puertos_lookalike import CoincidenciaRues
from app.modulos.intake.dominio.sugerencia_lookalike import Sugerencia

TOP = 3


@dataclass(frozen=True)
class Distribucion:
    sugerencia: Sugerencia
    ciiu: tuple[tuple[str, int], ...]  # top 3 (codigo, n)
    departamento: tuple[tuple[str, int], ...]  # top 3 (codigo DIVIPOLA, n)


def _top(cuenta: Counter[str]) -> tuple[tuple[str, int], ...]:
    # Empate: el código menor, para que el resultado no dependa del orden de entrada.
    return tuple(sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP])


def _activa(m: CoincidenciaRues) -> bool:
    return isinstance(m.estado_matricula, str) and m.estado_matricula.strip().upper() == "ACTIVA"


def agregar_distribucion(
    matches: Iterable[CoincidenciaRues],
    camara_a_departamento: Mapping[str, str],
    ciiu_validos: Collection[str] | None = None,
) -> Distribucion:
    """`ciiu_validos` (catálogo): un CIIU fuera de él no se sugiere, aunque la explicación lo cuente.

    Una cámara que no está en `camara_a_departamento` no suma al departamento: no se inventa.
    """
    por_nit: dict[str, CoincidenciaRues] = {}
    for m in matches:
        if _activa(m):
            por_nit.setdefault(m.nit, m)  # el mismo NIT desde dos nombres cuenta una vez
    ciiu = Counter(m.ciiu for m in por_nit.values() if m.ciiu)
    departamento = Counter(
        camara_a_departamento[m.camara] for m in por_nit.values() if m.camara in camara_a_departamento
    )
    top_ciiu, top_depto = _top(ciiu), _top(departamento)
    moda_ciiu = top_ciiu[0][0] if top_ciiu else None
    if moda_ciiu is not None and ciiu_validos is not None and moda_ciiu not in ciiu_validos:
        moda_ciiu = None
    return Distribucion(
        sugerencia=Sugerencia(ciiu=moda_ciiu, departamento=top_depto[0][0] if top_depto else None),
        ciiu=top_ciiu,
        departamento=top_depto,
    )
