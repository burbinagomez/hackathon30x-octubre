import pytest

from app.modulos.contacto.dominio.errores import PlantillaInvalida
from app.modulos.contacto.dominio.plantilla import componer, validar
from evals.scorers import forma

BASE = "Somos una agencia de carga en Bogotá y movemos importaciones para ferreterías como la suya."
REMITENTE = "Ana Pérez, Carga Sintética SAS"
URL_BAJA = "https://api.ejemplo.test/baja/TOKENDEESTE"
URL_OTRO = "https://api.ejemplo.test/baja/TOKENDEOTRO"
PRIVACIDAD = "https://web.ejemplo.test/privacidad"


def _cuerpo(canal="sitio_web", base=BASE, url_baja=URL_BAJA):
    return componer(base, REMITENTE, canal, url_baja, PRIVACIDAD)[1]


def test_mensaje_lleva_enlace_de_baja():
    cuerpo = _cuerpo()
    assert URL_BAJA in cuerpo
    assert "BAJA" in cuerpo
    validar(cuerpo, REMITENTE, URL_BAJA, PRIVACIDAD)


def test_asunto_no_vacio_y_sin_saltos():
    asunto, _ = componer(BASE, REMITENTE, "sitio_web", URL_BAJA, PRIVACIDAD)
    assert asunto and "\n" not in asunto and "\r" not in asunto


@pytest.mark.parametrize(("canal", "origen"), [
    ("sitio_web", "encontramos su contacto en su sitio web"),
    ("osm_contacto", "encontramos su contacto en un directorio público (OpenStreetMap)"),
])
def test_pie_completo(canal, origen):
    cuerpo = _cuerpo(canal)
    assert BASE in cuerpo
    assert REMITENTE in cuerpo
    assert origen in cuerpo
    assert PRIVACIDAD in cuerpo
    assert forma.mensaje({"cuerpo": cuerpo, "adjuntos": []}) is None


def test_canal_desconocido_no_compone():
    with pytest.raises(PlantillaInvalida, match="origen"):
        componer(BASE, REMITENTE, "comprado", URL_BAJA, PRIVACIDAD)


def test_url_de_baja_de_otro_contacto_no_valida():
    with pytest.raises(PlantillaInvalida, match="baja"):
        validar(_cuerpo(url_baja=URL_OTRO), REMITENTE, URL_BAJA, PRIVACIDAD)
    # Las dos URLs juntas tampoco: el mensaje lleva solo la de este contacto.
    with pytest.raises(PlantillaInvalida, match="baja"):
        validar(_cuerpo() + "\n" + URL_OTRO, REMITENTE, URL_BAJA, PRIVACIDAD)


@pytest.mark.parametrize(("quitar", "regla"), [
    (REMITENTE, "identificacion"),
    ("encontramos su contacto", "origen"),
    (PRIVACIDAD, "privacidad"),
])
def test_validar_exige_el_pie_completo(quitar, regla):
    with pytest.raises(PlantillaInvalida, match=regla):
        validar(_cuerpo().replace(quitar, "x"), REMITENTE, URL_BAJA, PRIVACIDAD)


def test_menos_de_100_palabras():
    corto = _cuerpo()
    validar(corto, REMITENTE, URL_BAJA, PRIVACIDAD)
    relleno = " ".join(["palabra"] * (100 - len(corto.split())))
    with pytest.raises(PlantillaInvalida, match="palabras"):
        validar(_cuerpo(base=BASE + " " + relleno), REMITENTE, URL_BAJA, PRIVACIDAD)
    validar(_cuerpo(base=BASE + " " + relleno.rsplit(" ", 1)[0]), REMITENTE, URL_BAJA, PRIVACIDAD)
