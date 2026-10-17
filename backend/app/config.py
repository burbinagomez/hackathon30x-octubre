import base64
import binascii
import json
import os
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings

# sbp_: access token del CLI. `migrar` ya no lo usa (usa SUPABASE_DB_URL), pero en la api sigue prohibido.
PREFIJOS_PROHIBIDOS = ("sb_publishable_", "sb_secret_", "sbp_")
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


def _es_postgres(valor: str) -> bool:
    # postgres o postgres.<ref> (pooler): el superusuario de `supabase db push`, que saltea RLS.
    try:
        url = urlsplit(valor)
    except ValueError:
        return False
    return url.scheme.startswith("postgres") and (url.username or "").split(".")[0] == "postgres"


def verificar_entorno() -> None:
    """Corta el arranque si api ve un secret que no le corresponde. Nombra la variable, nunca el valor."""
    for nombre, valor in os.environ.items():
        if (
            # Nombre de la era app_mig: se queda por si llega desde una guía o un Railway viejo.
            nombre == "MIGRATION_DATABASE_URL"
            or nombre.startswith("SUPABASE_")
            or valor.startswith(PREFIJOS_PROHIBIDOS)
            or _rol_jwt(valor) in ROLES_SUPABASE
            # Solo la conexión de api: los tests de integración tienen su admin en otra variable.
            or (nombre == "DATABASE_URL" and _es_postgres(valor))
        ):
            raise SecretProhibido(f"{nombre} no puede estar en el entorno de api")
