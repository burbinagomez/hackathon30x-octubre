"""Tokens firmados para la URL de baja y el Message-ID: el tenant y el contacto viajan firmados."""
import base64
import hashlib
import hmac
from uuid import UUID

_MAC = 16


def _mac(clave: bytes, proposito: str, crudo: bytes) -> bytes:
    return hmac.new(clave, proposito.encode() + b"\0" + crudo, hashlib.sha256).digest()[:_MAC]


def firmar(clave: bytes, proposito: str, tenant_id: UUID, contacto_id: UUID) -> str:
    crudo = tenant_id.bytes + contacto_id.bytes
    return base64.urlsafe_b64encode(crudo + _mac(clave, proposito, crudo)).decode().rstrip("=")


def verificar(clave: bytes, proposito: str, token: str) -> tuple[UUID, UUID] | None:
    """(tenant_id, contacto_id) si el token vale para ese propósito; None si no."""
    try:
        datos = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except ValueError:
        return None
    if len(datos) != 32 + _MAC:
        return None
    crudo, mac = datos[:32], datos[32:]
    if not hmac.compare_digest(mac, _mac(clave, proposito, crudo)):
        return None
    return UUID(bytes=crudo[:16]), UUID(bytes=crudo[16:])
