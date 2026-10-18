"""SettingsEmail: SMTP por variables, `EMAIL_MODO=prueba` por defecto y ningún secreto en repr ni en errores."""
import pytest
from pydantic import ValidationError

from app.config import SettingsEmail

CLAVE_SMTP = "re_clave_smtp_de_prueba_123"
BAJA_SECRET = "b" * 32


@pytest.fixture
def entorno(monkeypatch):
    for nombre, valor in {
        "DATABASE_URL": "postgresql+psycopg://app_rt@localhost/db",
        "CIFRADO_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "SMTP_HOST": "smtp.resend.com",
        "SMTP_USUARIO": "resend",
        "SMTP_CLAVE": CLAVE_SMTP,
        "REMITENTE": "Equipo <hola@ejemplo.test>",
        "BAJA_SECRET": BAJA_SECRET,
        "API_BASE_URL": "https://api.ejemplo.test",
    }.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.delenv("EMAIL_MODO", raising=False)
    monkeypatch.delenv("EMAIL_PRUEBA_DESTINOS", raising=False)
    monkeypatch.delenv("SMTP_SEGURIDAD", raising=False)
    return monkeypatch


def test_email_modo_por_defecto_es_prueba(entorno):
    s = SettingsEmail(_env_file=None)

    assert s.email_modo == "prueba"
    assert s.email_prueba_destinos == []


def test_destinos_de_prueba_separados_por_coma(entorno):
    entorno.setenv("EMAIL_PRUEBA_DESTINOS", " a@ejemplo.test, b@ejemplo.test ,")

    s = SettingsEmail(_env_file=None)

    assert s.email_prueba_destinos == ["a@ejemplo.test", "b@ejemplo.test"]


@pytest.mark.parametrize("modo", ["Real", "produccion", ""])
def test_modo_desconocido_no_arranca(entorno, modo):
    # Falla cerrado: un typo en Railway no puede quedar como "real".
    entorno.setenv("EMAIL_MODO", modo)

    with pytest.raises(ValidationError):
        SettingsEmail(_env_file=None)


def test_secretos_no_salen_en_repr(entorno):
    s = SettingsEmail(_env_file=None)

    assert CLAVE_SMTP not in repr(s)
    assert BAJA_SECRET not in repr(s)


def test_secretos_no_salen_en_el_error_de_validacion(entorno):
    entorno.setenv("SMTP_PORT", "no-es-puerto")

    with pytest.raises(ValidationError) as error:
        SettingsEmail(_env_file=None)

    assert CLAVE_SMTP not in str(error.value)


@pytest.mark.parametrize("host", ["smtp.resend.com", "10.0.0.5"])
def test_ninguna_solo_con_localhost(entorno, host):
    # Sin TLS solo contra el SMTP falso de los tests.
    entorno.setenv("SMTP_SEGURIDAD", "ninguna")
    entorno.setenv("SMTP_HOST", host)

    with pytest.raises(ValidationError):
        SettingsEmail(_env_file=None)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_ninguna_con_localhost_arranca(entorno, host):
    entorno.setenv("SMTP_SEGURIDAD", "ninguna")
    entorno.setenv("SMTP_HOST", host)

    assert SettingsEmail(_env_file=None).smtp_seguridad == "ninguna"


def test_baja_secret_corta_no_arranca(entorno):
    entorno.setenv("BAJA_SECRET", "corta")

    with pytest.raises(ValidationError):
        SettingsEmail(_env_file=None)


@pytest.mark.parametrize("url", ["http://api.ejemplo.test", "ftp://api.ejemplo.test", "api.ejemplo.test",
                                 "http://localhost.atacante.test", "https://"])
def test_api_base_url_exige_https(entorno, url):
    # El enlace de baja va en cada mail: en claro se puede leer o reescribir en el camino.
    entorno.setenv("API_BASE_URL", url)

    with pytest.raises(ValidationError, match="API_BASE_URL"):
        SettingsEmail(_env_file=None)


@pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1:8000"])
def test_api_base_url_http_solo_en_localhost(entorno, url):
    entorno.setenv("API_BASE_URL", url)

    assert SettingsEmail(_env_file=None).api_base_url == url
