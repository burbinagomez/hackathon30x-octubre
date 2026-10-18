"""Cifrado de datos sensibles (principio VI). Firma primero: el cuerpo llega con el verde de T018."""
from uuid import UUID


class Cifrador:
    def __init__(self, clave: str | None):
        pass

    def cifrar(self, columna: str, valor: str, tenant_id: UUID, lead_id: UUID) -> bytes:
        return b""

    def descifrar(self, columna: str, blob: bytes, tenant_id: UUID, lead_id: UUID) -> str:
        return ""
