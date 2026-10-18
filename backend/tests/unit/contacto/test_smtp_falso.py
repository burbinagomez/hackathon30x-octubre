"""El SMTP falso es la red de los tests de envío: si miente, todo lo de arriba miente."""
import smtplib

import pytest

from tests.smtp_falso import CLAVE_FALSA, USUARIO, SmtpFalso

MENSAJE = b"Subject: hola\r\n\r\ncuerpo\r\n"


def _mandar(falso: SmtpFalso, destinos: list[str]) -> None:
    with smtplib.SMTP(falso.host, falso.port, timeout=5) as smtp:
        smtp.login(USUARIO, CLAVE_FALSA)
        smtp.sendmail("ventas@ejemplo.test", destinos, MENSAJE)


def test_guarda_remitente_destinos_datos_y_credenciales():
    with SmtpFalso() as falso:
        _mandar(falso, ["a@ejemplo.test"])
    assert len(falso.mensajes) == 1
    recibido = falso.mensajes[0]
    assert recibido.remitente == "ventas@ejemplo.test"
    assert recibido.destinos == ["a@ejemplo.test"]
    assert b"Subject: hola" in recibido.datos
    assert falso.credenciales == [(USUARIO, CLAVE_FALSA)]


def test_rechaza_un_destino_con_550():
    with SmtpFalso(rechazar=frozenset({"no@ejemplo.test"})) as falso:
        with pytest.raises(smtplib.SMTPRecipientsRefused):
            _mandar(falso, ["no@ejemplo.test"])
    assert falso.mensajes == []


def test_corta_en_data():
    with SmtpFalso(cortar_en_data=True) as falso:
        with pytest.raises(smtplib.SMTPServerDisconnected):
            _mandar(falso, ["a@ejemplo.test"])
    assert falso.mensajes == []
