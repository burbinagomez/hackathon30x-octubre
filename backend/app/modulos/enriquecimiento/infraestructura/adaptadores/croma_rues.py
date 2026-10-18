from uuid import UUID

from app.modulos.enriquecimiento.dominio.puertos import VerificacionTitular


class CromaRues:
    """Bloqueado por P1/D11 (Fase 4): el endpoint configurado busca por NIT, no por nombre.
    Falla cerrado: sin consultar no asciende a juridica (pasaría a claro el nombre de una persona natural)."""

    def verificar(self, lead_id: UUID, nombre_normalizado: str, ciudad: str | None, pais: str) -> VerificacionTitular:
        return VerificacionTitular("desconocido", "sin_match")
