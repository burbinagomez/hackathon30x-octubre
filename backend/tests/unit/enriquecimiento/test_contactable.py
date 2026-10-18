from app.modulos.enriquecimiento.dominio.canal import elegir_canal
from app.modulos.enriquecimiento.dominio.contactable import calcular_contactable, es_contacto_nominal


def test_juridica_con_telefono_es_contactable():
    assert calcular_contactable("juridica", "sitio_web", None, False) == (True, None)


def test_juridica_con_email_es_contactable():
    assert calcular_contactable("juridica", None, "osm_contacto", False) == (True, None)


def test_juridica_sin_canal_no_es_contactable():
    assert calcular_contactable("juridica", None, None, False) == (False, "sin_canal_publicado")


def test_natural_nunca_es_contactable_aunque_tenga_canal():
    assert calcular_contactable("natural", "whatsapp_comercial", "sitio_web", False) == (False, "persona_natural")


def test_desconocido_se_trata_como_natural():
    assert calcular_contactable("desconocido", "whatsapp_comercial", "sitio_web", False) == (False, "persona_natural")


def test_contacto_nominal_no_es_contactable():
    assert es_contacto_nominal("juan.perez@empresa.com")
    assert es_contacto_nominal("JUAN.PEREZ@EMPRESA.COM")
    assert not es_contacto_nominal("info@empresa.com")

    assert calcular_contactable("juridica", None, "sitio_web", True) == (False, "contacto_nominal")
    assert calcular_contactable("juridica", None, "sitio_web", False) == (True, None)
    # El email nominal se descarta, pero el teléfono de la empresa sigue sirviendo.
    assert calcular_contactable("juridica", "sitio_web", "sitio_web", True) == (True, None)


def test_orden_de_razon_no_contactable():
    assert calcular_contactable("natural", None, "sitio_web", True) == (False, "persona_natural")
    assert calcular_contactable("natural", None, None, False) == (False, "persona_natural")
    assert calcular_contactable("juridica", None, None, True) == (False, "sin_canal_publicado")


def test_jerarquia_de_canal_sitio_web_reemplaza_osm():
    assert elegir_canal(("3001", "whatsapp_osm"), ("3002", "sitio_web")) == ("3002", "sitio_web")
    assert elegir_canal(("3001", "sitio_web"), ("3002", "osm_contacto")) == ("3001", "sitio_web")
    assert elegir_canal(("3001", "whatsapp_comercial"), ("3002", "sitio_web")) == ("3001", "whatsapp_comercial")
    # Mismo canal: se queda el que ya estaba.
    assert elegir_canal(("3001", "sitio_web"), ("3002", "sitio_web")) == ("3001", "sitio_web")
    assert elegir_canal(None, ("3002", "osm_contacto")) == ("3002", "osm_contacto")
    # Fetch fallido: el lead se queda con lo que ya tenía.
    assert elegir_canal(("3001", "osm_contacto"), None) == ("3001", "osm_contacto")
