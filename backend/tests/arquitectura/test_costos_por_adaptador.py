"""Principio VIII: todo adaptador de salida recibe un `RegistroCostos`. Acá, los jueces de `evals/jueces/`
y los canales de contacto de `app/modulos/contacto/infraestructura/`.

El test recorre los módulos que hay en la carpeta y no nombra a ningún adaptador en un import: uno nuevo entra solo.
"""
import importlib
import inspect
import pkgutil
import typing

import app.modulos.contacto.infraestructura
import evals.jueces
from app.modulos.costos.dominio.puertos import RegistroCostos

# Cerrada: un juez que no escribe costos tiene que estar acá con su razón, y si desaparece, el test avisa.
EXCLUIDOS = {"JuezFalso"}  # doble de tests: sin red ni gasto


def _adaptadores(paquete, metodo: str) -> dict[str, type]:
    clases = {}
    for modulo in pkgutil.iter_modules(paquete.__path__):
        m = importlib.import_module(f"{paquete.__name__}.{modulo.name}")
        for nombre, cls in inspect.getmembers(m, inspect.isclass):
            if cls.__module__ == m.__name__ and callable(getattr(cls, metodo, None)) \
                    and not getattr(cls, "_is_protocol", False):
                clases[nombre] = cls
    return clases


def _sin_registro(clases: dict[str, type], excluidos: set[str]) -> list[str]:
    return [n for n, cls in clases.items() if n not in excluidos
            and RegistroCostos not in typing.get_type_hints(cls.__init__).values()]


def test_todo_juez_recibe_registro_costos():
    jueces = _adaptadores(evals.jueces, "juzgar")

    # Sin esto nace verde con la carpeta vacía o sin el juez real.
    assert "JuezClaude" in jueces, f"jueces encontrados: {sorted(jueces)}"
    assert EXCLUIDOS <= set(jueces), "exclusión obsoleta: el juez excluido ya no existe"
    assert _sin_registro(jueces, EXCLUIDOS) == [], "jueces sin RegistroCostos en el constructor"


def test_todo_canal_de_contacto_recibe_registro_costos():
    canales = _adaptadores(app.modulos.contacto.infraestructura, "enviar")

    assert "SmtpEmail" in canales, f"canales encontrados: {sorted(canales)}"
    assert _sin_registro(canales, set()) == [], "canales sin RegistroCostos en el constructor"



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


def _adaptadores_de_intake() -> dict[str, type]:
    """Adaptadores de `intake/infraestructura/**`: toda clase propia con `generar` (GeneradorEstructurado) o
    `buscar_coincidencias` (BuscadorRazonSocial). Recorre el árbol: uno nuevo entra solo."""
    import app.modulos.intake.infraestructura as infra

    encontrados = {}
    for modulo in pkgutil.walk_packages(infra.__path__, infra.__name__ + "."):
        m = importlib.import_module(modulo.name)
        for nombre, cls in inspect.getmembers(m, inspect.isclass):
            if cls.__module__ == m.__name__ and not getattr(cls, "_is_protocol", False) \
                    and any(callable(getattr(cls, metodo, None)) for metodo in ("generar", "buscar_coincidencias")):
                encontrados[nombre] = cls
    return encontrados


def test_todo_adaptador_de_intake_recibe_registro_costos():
    adaptadores = _adaptadores_de_intake()

    assert "InterpretadorClaude" in adaptadores, f"adaptadores encontrados: {sorted(adaptadores)}"
    sin_registro = [n for n, cls in adaptadores.items()
                    if RegistroCostos not in typing.get_type_hints(cls.__init__).values()]
    assert sin_registro == [], f"adaptadores de intake sin RegistroCostos en el constructor: {sin_registro}"
