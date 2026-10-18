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
