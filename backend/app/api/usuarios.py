from fastapi import APIRouter, Depends

from app.api.sesion import sesion_actual

router = APIRouter()


@router.get("/usuarios/me")
def usuarios_me(sesion=Depends(sesion_actual)):
    _, acceso = sesion
    return {"idioma_usuario": acceso.idioma_usuario, "idioma_tenant": acceso.idioma_tenant}
