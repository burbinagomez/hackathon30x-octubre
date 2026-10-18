"""canal_preferido se valida contra `canales_contacto` del YAML: nunca un Literal en el código."""
import pytest

from app.api.canales import canal_habilitado

YAML = {
    "smtp_email": {"habilitado": True, "canal": "email"},
    "whatsapp_meta": {"habilitado": False, "canal": "whatsapp"},
}


def test_canal_de_una_entrada_habilitada_se_acepta():
    assert canal_habilitado("email", YAML) is True


def test_canal_de_una_entrada_deshabilitada_se_rechaza():
    assert canal_habilitado("whatsapp", YAML) is False


def test_si_el_yaml_habilita_whatsapp_se_acepta_sin_tocar_el_codigo():
    habilitado = {**YAML, "whatsapp_meta": {**YAML["whatsapp_meta"], "habilitado": True}}
    assert canal_habilitado("whatsapp", habilitado) is True  # un Literal["email"] lo seguiría rechazando


@pytest.mark.parametrize("canal", ["fax", "", "smtp_email", "EMAIL"])
def test_canal_que_ninguna_entrada_declara_se_rechaza(canal):
    assert canal_habilitado(canal, YAML) is False


def test_entrada_sin_clave_canal_no_habilita_nada():
    assert canal_habilitado("email", {"smtp_email": {"habilitado": True}}) is False
