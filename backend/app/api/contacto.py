"""Primer toque por email desde la api (007): vista previa, envío, respuesta y tasa. Lo mismo que la CLI `enviar`,
`respondio` y `tasa-respuesta`, para correrlo en Railway sin consola. Solo conteos y el texto del mensaje: nunca
la dirección de un destinatario. EMAIL_MODO=prueba (por defecto) manda solo a EMAIL_PRUEBA_DESTINOS."""
from decimal import Decimal
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.api.sesion import tenant_actual
from app.composicion import CONFIG
from app.config import SettingsEmail
from app.modulos.contacto.aplicacion.envio import EnviarABusqueda
from app.modulos.contacto.dominio.errores import MensajeCambio, SinVistaPrevia
from app.modulos.contacto.infraestructura.leads_contactables import LeadsContactablesPostgres
from app.modulos.contacto.infraestructura.repositorio_contactos import RepositorioContactosPostgres
from app.modulos.contacto.infraestructura.smtp_email import SmtpEmail
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos

router = APIRouter()


def _ajustes() -> SettingsEmail:
    try:
        return SettingsEmail()
    except ValidationError:  # sin SMTP_* o BAJA_SECRET: la api sigue viva, el envío no está disponible
        raise HTTPException(status_code=503, detail="email_no_configurado") from None


def _caso(request: Request, tenant_id: UUID) -> EnviarABusqueda:
    ajustes, e = _ajustes(), request.app.state
    tarifa = Decimal(str(yaml.safe_load((CONFIG / "tarifas.yaml").read_text())["email"]["usd_por_mensaje"]))
    return EnviarABusqueda(
        tenant_id, RepositorioContactosPostgres(e.engine, tenant_id),
        LeadsContactablesPostgres(e.engine, tenant_id, e.cifrador),
        SmtpEmail(ajustes, PostgresCostos(e.engine, tenant_id), tarifa),
        clave_baja=ajustes.baja_secret.get_secret_value().encode(), remitente=ajustes.remitente,
        url_api=ajustes.api_base_url, url_privacidad=ajustes.url_privacidad, modo=ajustes.email_modo,
        destinos_prueba=ajustes.email_prueba_destinos)


@router.post("/busquedas/{busqueda_id}/envio/vista-previa")
def vista_previa(busqueda_id: UUID, request: Request, rehacer: bool = False, tenant_id: UUID = Depends(tenant_actual)):
    """Aprueba los contactables de la búsqueda y muestra el mensaje. No manda nada (el --dry-run de la CLI)."""
    r = _caso(request, tenant_id).vista_previa(busqueda_id, rehacer=rehacer)
    return {"modo": r.modo, "aprobados": r.aprobados, "a_enviar": r.a_enviar, "asunto": r.asunto, "cuerpo": r.cuerpo}


@router.post("/busquedas/{busqueda_id}/envio")
def enviar(busqueda_id: UUID, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    try:
        return {"enviados": _caso(request, tenant_id).enviar(busqueda_id)}
    except SinVistaPrevia:
        raise HTTPException(status_code=409, detail="sin_vista_previa") from None
    except MensajeCambio:
        raise HTTPException(status_code=409, detail="mensaje_cambio") from None


@router.post("/contactos/{contacto_id}/respondio")
def respondio(contacto_id: UUID, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    if not RepositorioContactosPostgres(request.app.state.engine, tenant_id).marcar_respondio(contacto_id):
        raise HTTPException(status_code=404, detail="sin_envio")  # no hay un envío de ese contacto en este tenant
    return {"respondio": True}


@router.get("/contactos/tasa")
def tasa(request: Request, tenant_id: UUID = Depends(tenant_actual)):
    filas = RepositorioContactosPostgres(request.app.state.engine, tenant_id).tasa_por_canal()
    return {"items": [{"canal": c, "contactados": n, "respondieron": r, "tasa": None if t is None else str(t)}
                      for c, n, r, t in filas]}


@router.get("/busquedas/{busqueda_id}/contactos")
def contactos(busqueda_id: UUID, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    filas = RepositorioContactosPostgres(request.app.state.engine, tenant_id).de_busqueda(busqueda_id)
    return {"items": [{"id": str(i), "estado": e, "enviado_en": env and env.isoformat(),
                       "respondio_en": resp and resp.isoformat()} for i, e, env, resp in filas]}
