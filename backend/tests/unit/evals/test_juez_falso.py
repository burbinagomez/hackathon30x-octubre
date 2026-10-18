"""El doble del juez que usan los tests del runner: si miente, los tests del runner no prueban nada."""
import pytest

from evals.jueces.falso import JuezFalso
from evals.jueces.puerto import SalidaJuezInvalida, Veredicto


def test_devuelve_la_secuencia_programada_por_id_y_cuenta_llamadas():
    juez = JuezFalso({"a": [0.9, 0.8, 0.7], "b": [0.1]})

    salidas = [juez.juzgar("encaje_icp", {"id": "a"}).probabilidad for _ in range(3)]

    assert salidas == [0.9, 0.8, 0.7]
    assert juez.llamadas == {"a": 3}
    assert isinstance(juez.juzgar("encaje_icp", {"id": "b"}), Veredicto)
    assert juez.llamadas == {"a": 3, "b": 1}


def test_una_salida_invalida_programada_se_lanza():
    juez = JuezFalso({"a": [SalidaJuezInvalida("probabilidad: alta")]})

    with pytest.raises(SalidaJuezInvalida):
        juez.juzgar("encaje_icp", {"id": "a"})
    assert juez.llamadas == {"a": 1}


def test_no_es_determinista_por_defecto():
    # sabotaje: `determinista_si_se_demuestra = True` en JuezFalso → falla por assert (assert True is False).
    assert JuezFalso.determinista_si_se_demuestra is False
