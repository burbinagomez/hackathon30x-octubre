import base64
import binascii
import json
import os

from pydantic_settings import BaseSettings

PREFIJOS_PROHIBIDOS = ("sb_publishable_", "sb_secret_")
ROLES_SUPABASE = {"anon", "service_role"}


class Settings(BaseSettings):
    database_url: str


class SecretProhibido(RuntimeError):
    pass


def _rol_jwt(valor: str) -> str | None:
    # Sin verificar firma: solo importa el claim role de las keys legacy de Supabase.
    partes = valor.split(".")
    if len(partes) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4)))
    except (ValueError, binascii.Error):
        return None
    return payload.get("role") if isinstance(payload, dict) else None


def verificar_entorno() -> None:
    """Corta el arranque si api ve un secret que no le corresponde. Nombra la variable, nunca el valor."""
    for nombre, valor in os.environ.items():
        if (
            nombre == "MIGRATION_DATABASE_URL"
            or nombre.startswith("SUPABASE_")
            or valor.startswith(PREFIJOS_PROHIBIDOS)
            or _rol_jwt(valor) in ROLES_SUPABASE
        ):
            raise SecretProhibido(f"{nombre} no puede estar en el entorno de api")
