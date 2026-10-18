"""/baja/{token}: pública (RUTAS_PUBLICAS). GET confirma, POST da de baja (también one-click, RFC 8058)."""
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.modulos.contacto.aplicacion.baja import DarDeBaja
from app.modulos.contacto.infraestructura.repositorio_contactos import RepositorioContactosPostgres

router = APIRouter()


def _caso(request: Request) -> DarDeBaja:
    secreto = request.app.state.settings.baja_secret
    if secreto is None:
        raise HTTPException(404)
    engine = request.app.state.engine
    return DarDeBaja(secreto.get_secret_value().encode(), lambda tenant: RepositorioContactosPostgres(engine, tenant))


def _pagina(cuerpo: str) -> HTMLResponse:
    return HTMLResponse(f'<!doctype html><html lang="es"><meta charset="utf-8"><title>Baja</title><body>{cuerpo}</body></html>')


@router.get("/baja/{token}")
def confirmar_baja(token: str, request: Request):
    if not _caso(request).valido(token):
        raise HTTPException(404)
    t = escape(token, quote=True)
    return _pagina(f'<p>¿Querés dejar de recibir nuestros mensajes?</p>'
                   f'<form method="post" action="/baja/{t}"><button type="submit">Darme de baja</button></form>')


@router.post("/baja/{token}")
def dar_de_baja(token: str, request: Request):
    # Un token válido de un contacto que ya no existe también es 404: no se distingue de uno inventado.
    if not _caso(request)(token, "enlace"):
        raise HTTPException(404)
    return _pagina("<p>Listo: no vas a recibir más mensajes nuestros por ningún canal.</p>")
