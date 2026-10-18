"""Cifrado de datos sensibles en reposo (principio VI): AES-256-GCM con la clave del entorno.

AAD = `leads.<columna>:<tenant_id>:<lead_id>`: un valor no se puede mover de columna ni de fila (ni de
tenant) sin que la etiqueta GCM falle. El nonce de 12 bytes viaja como prefijo del blob.
"""
import os
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import decodificar_clave_de_cifrado

_NONCE = 12


class Cifrador:
    def __init__(self, clave: str | None):
        maestra = decodificar_clave_de_cifrado(clave)
        # Subclave propia para cifrar: la del HMAC del teléfono (Pulido) saldrá de la misma maestra con otro `info`.
        subclave = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"cifrado/aes-gcm/v1").derive(maestra)
        self._aes = AESGCM(subclave)

    @staticmethod
    def _aad(columna: str, tenant_id: UUID, lead_id: UUID) -> bytes:
        return f"leads.{columna}:{tenant_id}:{lead_id}".encode()

    def cifrar(self, columna: str, valor: str, tenant_id: UUID, lead_id: UUID) -> bytes:
        nonce = os.urandom(_NONCE)
        return nonce + self._aes.encrypt(nonce, valor.encode(), self._aad(columna, tenant_id, lead_id))

    def descifrar(self, columna: str, blob: bytes, tenant_id: UUID, lead_id: UUID) -> str:
        """Lanza cryptography.exceptions.InvalidTag si la clave, la columna o la fila no coinciden."""
        return self._aes.decrypt(blob[:_NONCE], blob[_NONCE:], self._aad(columna, tenant_id, lead_id)).decode()
