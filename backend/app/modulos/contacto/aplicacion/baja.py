"""Baja por enlace (spec 007 §5): el token firmado dice tenant y contacto; sin token válido no pasa nada."""
from collections.abc import Callable
from uuid import UUID

from app.modulos.contacto.dominio.puertos import RepositorioContactos
from app.modulos.contacto.dominio.tokens import verificar


class DarDeBaja:
    def __init__(self, clave: bytes, repo_de: Callable[[UUID], RepositorioContactos]):
        self._clave, self._repo_de = clave, repo_de

    def valido(self, token: str) -> bool:
        return verificar(self._clave, "baja", token) is not None

    def __call__(self, token: str, via: str) -> bool | None:
        """None si el token no es de baja o no verifica; si no, lo que diga el repo."""
        if (datos := verificar(self._clave, "baja", token)) is None:
            return None
        tenant, contacto = datos
        return self._repo_de(tenant).dar_de_baja(contacto, via)
