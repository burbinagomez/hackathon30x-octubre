import base64
import binascii
import json
import os
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# sbp_: access token del CLI. `migrar` ya no lo usa (usa SUPABASE_DB_URL), pero en la api sigue prohibido.
PREFIJOS_PROHIBIDOS = ("sb_publishable_", "sb_secret_", "sbp_")
ROLES_SUPABASE = {"anon", "service_role"}


class ConfigInvalida(RuntimeError):
    """Configuración que impide arrancar. El mensaje nombra la variable, nunca su valor."""


def decodificar_clave_de_cifrado(valor: str | None) -> bytes:
    """CIFRADO_KEY: 32 bytes en base64. Sin ella (o mal formada) no hay arranque; el error no trae el valor."""
    try:
        clave = base64.b64decode(valor or "", validate=True)
    except (binascii.Error, ValueError):
        clave = b""
    if len(clave) != 32:
        raise ConfigInvalida("CIFRADO_KEY debe ser 32 bytes en base64")
    return clave


class Settings(BaseSettings):
    # hide_input_in_errors: un valor inválido de una clave no puede salir en el ValidationError.
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    database_url: str
    # Sin default: la app no arranca sin clave de cifrado (principio VI).
    cifrado_key: SecretStr
    # SecretStr: no sale en repr ni en logs. Solo la CLI de búsqueda la usa.
    croma_api_key: SecretStr | None = None
    # Overpass: None = la constante del adaptador. repo_url va en el User-Agent (política de Overpass).
    overpass_url: str | None = None
    # datos.gov.co: None = la constante del adaptador / sin token (SODA limita por IP).
    datos_gov_co_url: str | None = None
    datos_gov_co_app_token: SecretStr | None = None
    repo_url: str = "https://github.com/burbinagomez/hackathon30x-octubre"
    # Supabase Auth: URLs públicas (JWKS del proyecto y emisor del token). Ningún secreto de firma en la api.
    # Obligatorias y no vacías: sin ellas la API no arranca (fallaría abierta o cerrada sin avisar).
    auth_jwks_url: str = Field(min_length=1)
    auth_issuer: str = Field(min_length=1)

    @field_validator("cifrado_key")
    @classmethod
    def _cifrado_key_valida(cls, valor: SecretStr) -> SecretStr:
        try:
            decodificar_clave_de_cifrado(valor.get_secret_value())
        except ConfigInvalida as error:
            raise ValueError(str(error)) from None
        return valor


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
