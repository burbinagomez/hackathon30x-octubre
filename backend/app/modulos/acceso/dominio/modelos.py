from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AccesoUsuario:
    """Lo que `tenant_de_usuario(sub)` sabe de un usuario: su tenant (nunca del token) y los dos idiomas."""

    tenant_id: UUID
    idioma_usuario: str | None
    idioma_tenant: str
