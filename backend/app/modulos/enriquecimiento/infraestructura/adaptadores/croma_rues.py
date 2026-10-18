from uuid import UUID

from app.modulos.enriquecimiento.dominio.puertos import VerificacionTitular


class CromaRues:
    """Bloqueado por P1/D11 (Fase 4): el endpoint configurado busca por NIT, no por nombre."""

    def verificar(self, lead_id: UUID, nombre_normalizado: str, ciudad: str | None) -> VerificacionTitular:
        return VerificacionTitular("juridica", "match_unico")
