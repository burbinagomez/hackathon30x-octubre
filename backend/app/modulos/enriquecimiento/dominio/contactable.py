from typing import Literal

from app.modulos.enriquecimiento.dominio.canal import CanalPublicado

TipoTitular = Literal["juridica", "natural", "desconocido"]
RazonNoContactable = Literal["persona_natural", "sin_canal_publicado", "contacto_nominal"]


def es_contacto_nominal(email: str) -> bool:
    """`nombre.apellido@`: dato de una persona, no de la empresa (regla 3 de cumplimiento-datos)."""
    return False


def calcular_contactable(tipo_titular: TipoTitular, telefono_canal: CanalPublicado | None,
                         email_canal: CanalPublicado | None, es_nominal: bool) -> tuple[bool, RazonNoContactable | None]:
    """Precedencia de la razón: persona_natural, sin_canal_publicado, contacto_nominal."""
    return True, None
