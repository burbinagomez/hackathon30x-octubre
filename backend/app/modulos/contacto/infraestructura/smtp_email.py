from app.modulos.contacto.dominio.modelos import MensajeSaliente, ResultadoEnvio


class SmtpEmail:
    canal = "email"

    def enviar(self, mensaje: MensajeSaliente) -> ResultadoEnvio:
        raise NotImplementedError
