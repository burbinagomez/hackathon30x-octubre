"""Scorers de forma: deterministas, sin juez. Cada fallo devuelve el nombre de la regla (motivo forma:<regla>).

El mensaje sigue la regla 7 de cumplimiento-datos; se parte de uno válido y se rompe una regla por test.
"""
import pytest

from evals.scorers import forma

# --- Encaje ----------------------------------------------------------------------------------

def test_salida_sin_probabilidad_falla():
    assert forma.encaje({"razon": "vende alimentos"}) == "probabilidad"
    assert forma.encaje({"probabilidad": "alta", "razon": "x"}) == "probabilidad"
    assert forma.encaje({"probabilidad": True, "razon": "x"}) == "probabilidad"


@pytest.mark.parametrize("p", [-0.1, 1.2])
def test_probabilidad_fuera_de_rango_falla(p):
    assert forma.encaje({"probabilidad": p, "razon": "x"}) == "rango"


@pytest.mark.parametrize("p", [0, 0.5, 1])
def test_salida_valida_pasa(p):
    assert forma.encaje({"probabilidad": p, "razon": "vende alimentos"}) is None


# --- Mensaje ---------------------------------------------------------------------------------

BASE = (
    "Hola, soy Ana de Panaderia Sintetica SAS. Le escribo para ofrecerle pan para su tienda. "
    "Encontramos su contacto en su sitio web. ¿Le interesa una muestra? "
    "Si no quiere recibir mas mensajes, responda BAJA. Aviso de privacidad: https://ejemplo.test/privacidad"
)


def _mensaje(cuerpo: str = BASE, adjuntos=None) -> dict:
    return {"asunto": "Pan para su tienda", "cuerpo": cuerpo, "adjuntos": [] if adjuntos is None else adjuntos}


def _con_palabras(n: int) -> str:
    faltan = n - len(BASE.split())
    assert faltan >= 0
    return BASE + " pan" * faltan


def test_mensaje_valido_pasa():
    assert forma.mensaje(_mensaje()) is None


def test_cien_palabras_o_mas_falla():
    assert forma.mensaje(_mensaje(_con_palabras(99))) is None
    assert forma.mensaje(_mensaje(_con_palabras(100))) == "palabras"


def test_sin_opt_out_falla():
    assert forma.mensaje(_mensaje(BASE.replace("Si no quiere recibir mas mensajes, responda BAJA. ", ""))) == "opt_out"


def test_sin_origen_del_dato_falla():
    assert forma.mensaje(_mensaje(BASE.replace("Encontramos su contacto en su sitio web. ", ""))) == "origen_del_dato"


def test_dos_preguntas_falla():
    # ¿…? es una sola pregunta: se cuentan los "?".
    assert forma.mensaje(_mensaje(BASE.replace("muestra?", "muestra? ¿Y un catalogo?"))) == "preguntas"


def test_con_adjuntos_falla():
    assert forma.mensaje(_mensaje(adjuntos=["catalogo.pdf"])) == "adjuntos"


def test_sin_enlace_a_privacidad_falla():
    assert forma.mensaje(_mensaje(BASE.replace(" Aviso de privacidad: https://ejemplo.test/privacidad", ""))) == "privacidad"
