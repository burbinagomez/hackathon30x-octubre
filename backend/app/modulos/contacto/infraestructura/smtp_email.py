"""Canal email por SMTP genérico (Resend en producción). La dirección y la clave nunca salen a logs ni excepciones."""
import smtplib
import ssl
from decimal import Decimal
from email.message import EmailMessage
from email.utils import parseaddr

from app.config import SettingsEmail
from app.modulos.contacto.dominio.errores import CanalNoDisponible
from app.modulos.contacto.dominio.modelos import MensajeSaliente, ResultadoEnvio
from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos

_TIMEOUT = 20


class SmtpEmail:
    canal = "email"

    def __init__(self, ajustes: SettingsEmail, costos: RegistroCostos, tarifa: Decimal):
        self._ajustes, self._costos, self._tarifa = ajustes, costos, tarifa

    def enviar(self, mensaje: MensajeSaliente) -> ResultadoEnvio:
        # Costo antes del SMTP: un intento que falla a mitad igual consumió cupo del proveedor.
        self._costos.registrar(OperacionCosto(
            tipo="email_envio", unidades=Decimal(1), costo_unitario=self._tarifa, moneda="USD",
            proveedor="smtp", fuente="smtp_email", canal=self.canal, lead_id=mensaje.lead_id,
            lote_id=mensaje.busqueda_id, gratis=True))
        try:
            with self._conectar() as smtp:
                smtp.login(self._ajustes.smtp_usuario, self._ajustes.smtp_clave.get_secret_value())
                smtp.send_message(self._armar(mensaje))
        except (smtplib.SMTPException, OSError) as e:
            # from None: la causa de smtplib trae la dirección rechazada.
            raise CanalNoDisponible(f"smtp: {type(e).__name__}") from None
        return ResultadoEnvio(enviado=True)

    def _conectar(self) -> smtplib.SMTP:
        a = self._ajustes
        if a.smtp_seguridad == "ssl":
            return smtplib.SMTP_SSL(a.smtp_host, a.smtp_port, timeout=_TIMEOUT, context=ssl.create_default_context())
        smtp = smtplib.SMTP(a.smtp_host, a.smtp_port, timeout=_TIMEOUT)
        if a.smtp_seguridad == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        return smtp

    def _armar(self, m: MensajeSaliente) -> EmailMessage:
        direccion = parseaddr(self._ajustes.remitente)[1]
        url_baja = f"{self._ajustes.api_base_url.rstrip('/')}/baja/{m.token_baja}"
        msg = EmailMessage()
        msg["From"] = self._ajustes.remitente
        msg["To"] = m.direccion
        msg["Subject"] = m.asunto
        msg["Message-ID"] = f"<b.{m.token_msgid}@{direccion.rpartition('@')[2]}>"
        msg["List-Unsubscribe"] = f"<mailto:{direccion}?subject=BAJA%20{m.token_baja}>, <{url_baja}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg.set_content(m.cuerpo)
        return msg
