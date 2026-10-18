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


# DaptaCSV (puerto Calificador) queda afuera a propósito: no hace ninguna operación de salida, solo lee un CSV
# que alguien ya descargó. La llamada la hace Dapta, no este adaptador; el minuto se cobra al importar el
# resultado (app.modulos.calificacion.aplicacion.importar_calificaciones), que sí recibe RegistroCostos (008, plan.md).
EXCLUIDOS_CALIFICADORES = {"DaptaCSV"}


def _calificadores() -> dict[str, type]:
    import importlib
    import app.modulos.calificacion.infraestructura as paquete

    calificadores = {}
    for modulo in pkgutil.iter_modules(paquete.__path__):
        m = importlib.import_module(f"{paquete.__name__}.{modulo.name}")
        for nombre, cls in inspect.getmembers(m, inspect.isclass):
            if cls.__module__ == m.__name__ and callable(getattr(cls, "leer_resultados", None)):
                calificadores[nombre] = cls
    return calificadores


def test_todo_calificador_recibe_registro_costos_salvo_los_excluidos():
    calificadores = _calificadores()

    assert "DaptaCSV" in calificadores, f"calificadores encontrados: {sorted(calificadores)}"
    assert EXCLUIDOS_CALIFICADORES <= set(calificadores), "exclusión obsoleta: el adaptador excluido ya no existe"
    sin_registro = [n for n, cls in calificadores.items() if n not in EXCLUIDOS_CALIFICADORES
                    and RegistroCostos not in typing.get_type_hints(cls.__init__).values()]
    assert sin_registro == [], f"calificadores sin RegistroCostos en el constructor: {sin_registro}"
