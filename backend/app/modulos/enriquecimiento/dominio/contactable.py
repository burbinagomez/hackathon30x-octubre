import re
from typing import Literal

from app.modulos.enriquecimiento.dominio.canal import CanalPublicado

TipoTitular = Literal["juridica", "natural", "desconocido"]
RazonNoContactable = Literal["persona_natural", "sin_canal_publicado", "contacto_nominal"]

_NOMINAL = re.compile(r"^[a-z]+\.[a-z]+@", re.I)


def es_contacto_nominal(email: str) -> bool:
    """`nombre.apellido@`: dato de una persona, no de la empresa (regla 3 de cumplimiento-datos)."""
    return bool(_NOMINAL.match(email))


def calcular_contactable(tipo_titular: TipoTitular, telefono_canal: CanalPublicado | None,
                         email_canal: CanalPublicado | None, es_nominal: bool) -> tuple[bool, RazonNoContactable | None]:
    """Precedencia de la razón: persona_natural, sin_canal_publicado, contacto_nominal."""
    if tipo_titular != "juridica":
        return False, "persona_natural"
    if telefono_canal is None and email_canal is None:
        return False, "sin_canal_publicado"
    if telefono_canal is None and es_nominal:
        return False, "contacto_nominal"
    return True, None
