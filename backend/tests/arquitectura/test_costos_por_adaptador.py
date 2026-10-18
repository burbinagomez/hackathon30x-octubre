"""Principio VIII: todo adaptador de salida recibe un `RegistroCostos`. Acá, los jueces de `evals/jueces/`.

El test recorre los módulos que hay en la carpeta y no nombra a ningún juez en un import: un juez nuevo entra solo.
"""
import importlib
import inspect
import pkgutil
import typing

import evals.jueces
from app.modulos.costos.dominio.puertos import RegistroCostos

# Cerrada: un juez que no escribe costos tiene que estar acá con su razón, y si desaparece, el test avisa.
EXCLUIDOS = {"JuezFalso"}  # doble de tests: sin red ni gasto


def _jueces() -> dict[str, type]:
    jueces = {}
    for modulo in pkgutil.iter_modules(evals.jueces.__path__):
        m = importlib.import_module(f"evals.jueces.{modulo.name}")
        for nombre, cls in inspect.getmembers(m, inspect.isclass):
            if cls.__module__ == m.__name__ and callable(getattr(cls, "juzgar", None)) \
                    and not getattr(cls, "_is_protocol", False):
                jueces[nombre] = cls
    return jueces


def test_todo_juez_recibe_registro_costos():
    jueces = _jueces()

    # Sin esto nace verde con la carpeta vacía o sin el juez real.
    assert "JuezClaude" in jueces, f"jueces encontrados: {sorted(jueces)}"
    assert EXCLUIDOS <= set(jueces), "exclusión obsoleta: el juez excluido ya no existe"
    sin_registro = [n for n, cls in jueces.items() if n not in EXCLUIDOS
                    and RegistroCostos not in typing.get_type_hints(cls.__init__).values()]
    assert sin_registro == [], f"jueces sin RegistroCostos en el constructor: {sin_registro}"
