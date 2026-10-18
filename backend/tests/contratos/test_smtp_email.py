"""Contrato de `smtp_email` contra el SMTP falso: headers de baja, auth, costo antes del SMTP y la dirección fuera de todo."""
import email
from email import policy
import logging
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import SettingsEmail
from app.modulos.contacto.dominio.errores import CanalNoDisponible, DestinatarioInvalido
from app.modulos.contacto.dominio.modelos import LeadContactable, MensajeSaliente
from app.modulos.contacto.infraestructura.smtp_email import SmtpEmail
from tests.falsos import RegistroCostosFalso
from tests.smtp_falso import CLAVE_FALSA, USUARIO, SmtpFalso

DESTINO = "compras@ferreteria-sintetica.test"
REMITENTE = "hola@agencia-sintetica.test"


def _ajustes(falso: SmtpFalso | None = None, **extra) -> SettingsEmail:
    base = dict(
        _env_file=None,
        database_url="postgresql+psycopg://app_rt@localhost/db",
        cifrado_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        smtp_host=falso.host if falso else "127.0.0.1",
        smtp_port=falso.port if falso else 1,
        smtp_usuario=USUARIO,
        smtp_clave=CLAVE_FALSA,
        smtp_seguridad="ninguna",
        remitente=f"Ana Pérez <{REMITENTE}>",
        baja_secret="b" * 32,
        api_base_url="https://api.ejemplo.test",
        url_privacidad="https://agencia-sintetica.test/privacidad",
    )
    return SettingsEmail(**(base | extra))


def _mensaje(direccion: str = DESTINO, asunto: str = "Consulta de Ana Pérez") -> MensajeSaliente:
    return MensajeSaliente(contacto_id=uuid4(), lead_id=uuid4(), busqueda_id=uuid4(),
                           asunto=asunto, cuerpo="Hola.\nResponda BAJA para no recibir más.\n",
                           token_baja="TOKBAJA", token_msgid="TOKMSG", direccion=direccion)


def _enviar(falso: SmtpFalso | None, m: MensajeSaliente | None = None):
    costos = RegistroCostosFalso()
    canal = SmtpEmail(_ajustes(falso), costos, Decimal("0.0"))
    return canal, costos, canal.enviar(m or _mensaje())


def test_headers_list_unsubscribe_y_message_id():
    with SmtpFalso() as falso:
        _, _, resultado = _enviar(falso)
    assert resultado.enviado is True
    [recibido] = falso.mensajes
    assert recibido.remitente == REMITENTE and recibido.destinos == [DESTINO]
    msg = email.message_from_bytes(recibido.datos, policy=policy.default)
    assert msg["Message-ID"] == "<b.TOKMSG@agencia-sintetica.test>"
    assert msg["List-Unsubscribe"] == (f"<mailto:{REMITENTE}?subject=BAJA%20TOKBAJA>, "
                                       "<https://api.ejemplo.test/baja/TOKBAJA>")
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert msg["Subject"] == "Consulta de Ana Pérez"
    assert msg.get_content_type() == "text/plain" and not msg.is_multipart()
    assert "BAJA" in msg.get_content()


def test_autentica_con_usuario_y_clave():
    with SmtpFalso() as falso:
        _enviar(falso)
    assert falso.credenciales == [(USUARIO, CLAVE_FALSA)]


@pytest.mark.parametrize("falla", ["rechazo", "corte", "sin_servidor"])
def test_error_de_transporte_es_canal_no_disponible_sin_direccion(falla):
    if falla == "sin_servidor":
        with pytest.raises(CanalNoDisponible) as e:
            _enviar(None)
    else:
        kw = {"rechazar": frozenset({DESTINO})} if falla == "rechazo" else {"cortar_en_data": True}
        with SmtpFalso(**kw) as falso, pytest.raises(CanalNoDisponible) as e:
            _enviar(falso)
    assert DESTINO not in str(e.value) and DESTINO not in repr(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__


def test_costo_se_registra_aunque_smtp_falle():
    m, costos = _mensaje(), RegistroCostosFalso()
    with SmtpFalso(rechazar=frozenset({DESTINO})) as falso, pytest.raises(CanalNoDisponible):
        SmtpEmail(_ajustes(falso), costos, Decimal("0.0")).enviar(m)
    [op] = costos.filas
    assert (op.tipo, op.unidades, op.canal, op.lead_id, op.lote_id, op.gratis) == \
        ("email_envio", 1, "email", m.lead_id, m.busqueda_id, True)
    assert type(op.costo_unitario) is Decimal and type(op.unidades) is Decimal


def test_costo_se_registra_antes_del_smtp():
    """Si el registro de costos falla, no sale nada por SMTP: el orden es costo → envío."""
    class CostosQueFallan(RegistroCostosFalso):
        def registrar(self, op):
            raise RuntimeError("libro caído")

    with SmtpFalso() as falso, pytest.raises(RuntimeError):
        SmtpEmail(_ajustes(falso), CostosQueFallan(), Decimal("0.0")).enviar(_mensaje())
    assert falso.mensajes == []


def test_contacto_no_aparece_en_logs(caplog, capsys):
    caplog.set_level(logging.DEBUG)
    with SmtpFalso(rechazar=frozenset({DESTINO})) as falso, pytest.raises(CanalNoDisponible) as e:
        _enviar(falso)
    salida = caplog.text + capsys.readouterr().err + str(e.value) + repr(e.value)
    salida += repr(LeadContactable(uuid4(), "sitio_web", DESTINO)) + repr(_mensaje()) + repr(_ajustes())
    assert DESTINO not in salida
    assert CLAVE_FALSA not in salida


def test_ninguna_solo_con_localhost():
    with pytest.raises(ValidationError, match="ninguna"):
        _ajustes(smtp_host="smtp.resend.com")
    assert _ajustes(smtp_host="localhost").smtp_seguridad == "ninguna"


@pytest.mark.parametrize("direccion", [
    f"{DESTINO}, otro@atacante.test",
    f"{DESTINO}; otro@atacante.test",
    f"{DESTINO},",
    f"Compras <{DESTINO}>",
    f"<{DESTINO}>",
    f"{DESTINO}\r\nBcc: otro@atacante.test",
    "compras @ferreteria-sintetica.test",
    "compras",
    "compras@",
    "@ferreteria-sintetica.test",
    "compras@@ferreteria-sintetica.test",
    "",
])
def test_direccion_que_no_es_una_sola_casilla_no_se_envia_ni_cobra(direccion):
    """La dirección viene raspada de un tercero: una coma no puede sumar un destinatario sin base legal."""
    costos = RegistroCostosFalso()
    with SmtpFalso() as falso, pytest.raises(DestinatarioInvalido) as e:
        SmtpEmail(_ajustes(falso), costos, Decimal("0.0")).enviar(_mensaje(direccion))
    assert falso.mensajes == [] and costos.filas == []
    assert "atacante" not in str(e.value) + repr(e.value)
    assert e.value.__cause__ is None and (e.value.__context__ is None or e.value.__suppress_context__)


def test_crlf_en_asunto_es_destinatario_invalido_sin_costo():
    costos = RegistroCostosFalso()
    with SmtpFalso() as falso, pytest.raises(DestinatarioInvalido) as e:
        SmtpEmail(_ajustes(falso), costos, Decimal("0.0")).enviar(_mensaje(asunto="Hola\r\nBcc: otro@atacante.test"))
    assert falso.mensajes == [] and costos.filas == []
    assert "atacante" not in str(e.value) + repr(e.value)
    assert e.value.__cause__ is None and (e.value.__context__ is None or e.value.__suppress_context__)


def test_destinatario_invalido_no_es_canal_no_disponible():
    # Uno se reintenta y el otro nunca: no pueden confundirse en un except.
    assert not issubclass(DestinatarioInvalido, CanalNoDisponible)
    assert not issubclass(CanalNoDisponible, DestinatarioInvalido)


def test_falla_en_quit_despues_de_aceptado_cuenta_como_enviado():
    """El servidor ya aceptó el DATA: un reintento duplicaría el mail."""
    with SmtpFalso(fallar_en_quit=True) as falso:
        _, costos, resultado = _enviar(falso)
    assert resultado.enviado is True
    assert len(falso.mensajes) == 1 and len(costos.filas) == 1


def test_sobre_sale_de_la_direccion_y_no_del_encabezado_to(monkeypatch):
    """Segunda defensa: aunque la validación dejara pasar una coma, el sobre lleva un solo RCPT."""
    from app.modulos.contacto.infraestructura import smtp_email
    monkeypatch.setattr(smtp_email, "getaddresses", lambda d: [("", d[0])])
    monkeypatch.setattr(smtp_email, "_CASILLA", type("Todo", (), {"fullmatch": staticmethod(lambda d: True)}))
    with SmtpFalso() as falso:
        _enviar(falso, _mensaje(f"{DESTINO}, otro@atacante.test"))
    [recibido] = falso.mensajes
    assert len(recibido.destinos) == 1 and "otro@atacante.test" not in recibido.destinos
