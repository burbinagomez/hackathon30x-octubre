class IntakeError(Exception):
    """Base de los errores de intake. Los mensajes llevan códigos, nunca la frase ni la respuesta del modelo."""


class SalidaIntakeInvalida(IntakeError):
    """La salida del modelo no cumple el esquema. Se reintenta una vez; al segundo fallo llega a la API."""


class FraseFueraDeRango(IntakeError):
    """La frase está vacía o pasa de MAX_FRASE caracteres."""


class ErrorGeneracion(IntakeError):
    """El proveedor de IA no respondió (red, 4xx/5xx). `codigo` es una etiqueta (`red`, `http_401`), no un mensaje."""

    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo


class IntakeFueraDeRango(IntakeError):
    """La lista pegada no trae de 5 a 50 nombres."""
