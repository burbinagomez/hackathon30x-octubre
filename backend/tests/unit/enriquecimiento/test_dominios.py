"""Candidatos de dominio desde la razón social y verificación de la página (006, enmienda buscador de sitio web). Puro."""
import pytest

from app.modulos.enriquecimiento.dominio.dominios import candidatos_de_dominio, verifica_pagina


def test_razon_social_simple_da_pegado_y_con_guion_en_los_tres_tld():
    assert candidatos_de_dominio("GRUPO PROCESSA S.A.S") == (
        "grupoprocessa.com.co", "grupoprocessa.com", "grupoprocessa.co",
        "grupo-processa.com.co", "grupo-processa.com", "grupo-processa.co")


def test_una_sola_palabra_no_repite_la_variante_con_guion():
    assert candidatos_de_dominio("Andinos SAS") == ("andinos.com.co", "andinos.com", "andinos.co")


def test_tildes_mayusculas_y_puntuacion_se_normalizan():
    assert candidatos_de_dominio("Logística & Carga Ñandú Ltda.")[0] == "logisticacarganandu.com.co"


@pytest.mark.parametrize("nombre", ["ANDINOS SAS EN LIQUIDACION", "ANDINOS S.A.S. EN REORGANIZACION", "Andinos LTDA",
                                    "ANDINOS EN LIQUIDACION SAS", "Andinos S.A."])
def test_sufijos_y_estados_societarios_no_entran_al_dominio(nombre):
    assert candidatos_de_dominio(nombre) == ("andinos.com.co", "andinos.com", "andinos.co")


def test_mas_de_tres_palabras_agrega_las_dos_primeras_juntas():
    candidatos = candidatos_de_dominio("Transportes Andinos Del Valle SAS")
    assert "transportesandinos.com.co" in candidatos
    assert "transportesandinosdelvalle.com.co" in candidatos


def test_tres_palabras_o_menos_no_agrega_las_dos_primeras():
    assert "transportesandinos.com" not in candidatos_de_dominio("Transportes Andinos Valle SAS")


def test_tope_de_seis_candidatos():
    assert len(candidatos_de_dominio("Transportes Andinos Del Valle Del Cauca SAS")) == 6


@pytest.mark.parametrize("nombre", ["COMERCIAL SAS", "Grupo S.A.S.", "INVERSIONES LTDA", "Servicios SAS", "Grupo Servicios SAS",
                                    "EN LIQUIDACION", "SAS", ""])
def test_solo_palabras_genericas_no_da_candidatos(nombre):
    assert candidatos_de_dominio(nombre) == ()


def test_generica_acompanada_de_nombre_propio_si_vale():
    assert candidatos_de_dominio("Comercial Processa SAS")[0] == "comercialprocessa.com.co"


def test_sin_duplicados():
    candidatos = candidatos_de_dominio("Transportes Andinos Del Valle SAS")
    assert len(candidatos) == len(set(candidatos))


PAGINA = "<html><head><title>Inicio</title></head><body><p>Bienvenidos a Grupo Processa</p></body></html>"


def test_verifica_por_razon_social_sin_sufijo():
    assert verifica_pagina(PAGINA, None, "GRUPO PROCESSA S.A.S.") == "razon_social"


def test_verifica_por_razon_social_ignorando_tildes_y_mayusculas():
    assert verifica_pagina("<p>LOGÍSTICA ÑANDÚ</p>", None, "Logistica Nandu SAS") == "razon_social"


@pytest.mark.parametrize("texto", ["NIT 900123456-7", "NIT: 900.123.456", "nit 900123456", "N.I.T. 900.123.456-7"])
def test_verifica_por_nit_con_o_sin_puntos(texto):
    assert verifica_pagina(f"<footer>{texto}</footer>", "900123456", "Otra Razon SAS") == "nit"


def test_el_nit_gana_sobre_la_razon_social():
    assert verifica_pagina(PAGINA + "NIT 900123456", "900123456", "GRUPO PROCESSA SAS") == "nit"


def test_pagina_que_no_menciona_la_empresa_no_verifica():
    assert verifica_pagina("<html><body>Dominio en venta. Contacto: ventas</body></html>", "900123456", "GRUPO PROCESSA SAS") is None


def test_nit_que_es_parte_de_un_numero_mas_largo_no_cuenta():
    assert verifica_pagina("<p>Ref 19001234567</p>", "900123456", "Otra Razon SAS") is None


def test_razon_social_parcial_no_verifica():
    assert verifica_pagina("<p>Grupo Empresarial</p>", None, "Grupo Processa SAS") is None


def test_palabra_dentro_de_otra_no_verifica():
    assert verifica_pagina("<p>andinosa</p>", None, "Andinos SAS") is None


def test_razon_social_vacia_o_solo_sufijo_no_verifica():
    assert verifica_pagina("<p>SAS sas</p>", None, "S.A.S.") is None


def test_nit_demasiado_corto_no_verifica():
    assert verifica_pagina("<p>123</p>", "123", "Otra Razon SAS") is None
