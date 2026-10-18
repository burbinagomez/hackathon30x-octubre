"""Bearer → VerificadorToken → tenant_de_usuario(sub). El tenant sale de `usuarios`, jamás del token ni del request.

Sin logs ni detalles de excepción: ni el token ni el motivo del rechazo salen de acá.
"""
import re
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from app.modulos.acceso.dominio.errores import JwksInaccesible, TokenInvalido
from app.modulos.acceso.dominio.modelos import AccesoUsuario
from app.modulos.acceso.infraestructura.repositorio_usuarios import tenant_de_usuario

BEARER = re.compile(r"Bearer (\S+)")  # un solo espacio y esa mayúscula: lo demás es 401


def _no_autenticado() -> HTTPException:
    return HTTPException(status_code=401, detail="no_autenticado")


def sesion_actual(request: Request) -> tuple[UUID, AccesoUsuario]:
    coincide = BEARER.fullmatch(request.headers.get("authorization", ""))
    if coincide is None:
        raise _no_autenticado()
    try:
        sub = request.app.state.verificador.verificar(coincide.group(1))
    except TokenInvalido:
        raise _no_autenticado() from None
    except JwksInaccesible:
        raise HTTPException(status_code=503, detail="auth_no_disponible") from None
    acceso = tenant_de_usuario(request.app.state.engine, sub)
    if acceso is None:
        raise HTTPException(status_code=403, detail="sin_acceso")
    return sub, acceso


def tenant_actual(sesion: tuple[UUID, AccesoUsuario] = Depends(sesion_actual)) -> UUID:
    return sesion[1].tenant_id
