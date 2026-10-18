"""Suite de contrato del puerto `Juez`: todo adaptador la pasa.

`[claude]` corre con la Messages API falsa (sin red); nació rojo contra el stub de T013 y está verde desde T018.
`[falso]` nace verde: `JuezFalso` existe desde T009 y no se reimplementa acá.
`test_registra_costo` es solo `[claude]`: `JuezFalso` es la exclusión cerrada de test_costos_por_adaptador.py.
"""
import pytest

from evals.jueces.falso import JuezFalso
from evals.jueces.puerto import Veredicto
from tests.anthropic_falso import CASO, juez
from tests.falsos import RegistroCostosFalso


def _construir(nombre, costos):
    if nombre == "claude":
        return juez(costos, [])
    return JuezFalso({CASO["id"]: [0.8]})  # sabotaje probado: [1.5] -> "assert 1.5 <= 1.0"


@pytest.mark.parametrize("nombre", ["claude", "falso"])
def test_devuelve_probabilidad_en_rango(nombre):
    veredicto = _construir(nombre, RegistroCostosFalso()).juzgar("encaje_icp", CASO)

    assert isinstance(veredicto, Veredicto)
    assert 0.0 <= veredicto.probabilidad <= 1.0
    assert isinstance(veredicto.razon, str)


@pytest.mark.parametrize("nombre", ["claude"])
def test_registra_costo(nombre):
    costos = RegistroCostosFalso()
    _construir(nombre, costos).juzgar("encaje_icp", CASO)

    assert len(costos.filas) > 0
    assert all(f.fuente == "evals" and f.unidades >= 0 for f in costos.filas)
