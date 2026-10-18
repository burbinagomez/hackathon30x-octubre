from uuid import UUID


def firmar(clave: bytes, proposito: str, tenant_id: UUID, contacto_id: UUID) -> str:
    raise NotImplementedError


def verificar(clave: bytes, proposito: str, token: str) -> tuple[UUID, UUID] | None:
    """(tenant_id, contacto_id) si el token vale para ese propósito; None si no."""
    raise NotImplementedError
