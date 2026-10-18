"""Lista de búsquedas y de leads de una búsqueda (solo lectura). El tenant sale SIEMPRE de `tenant_actual`.

Nunca descifra: el repo no lee las columnas cifradas, así que no hay nombre de naturales, dirección ni contacto que
devolver. Sin logs de datos de leads.
"""
from typing import Annotated
from uuid import UUID

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.sesion import tenant_actual
from app.modulos.descubrimiento.dominio.modelos import LeadListado, PaginaLeads
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres

router = APIRouter()

TAMANO_MAXIMO = 100


def _repo(request: Request, tenant_id: UUID) -> RepositorioLeadsPostgres:
    estado = request.app.state
    return RepositorioLeadsPostgres(estado.engine, tenant_id, estado.cifrador)


def _item(l: LeadListado) -> dict:
    return {
        "id": str(l.id), "nombre": l.nombre, "tipo_titular": l.tipo_titular, "fuentes": list(l.fuentes),
        "licencias": list(l.licencias), "ciudad": l.ciudad, "tiene_web": l.tiene_web,
        "tiene_telefono": l.tiene_telefono, "tiene_email": l.tiene_email,  # None = sin dato; nunca el valor
    }


def _fuentes_conocidas(request: Request) -> set[str]:
    registro = request.app.state.registro
    return set(registro.fuentes) | set(registro.sin_implementacion)


def _cuerpo(r: PaginaLeads) -> dict:
    return {
        "items": [_item(l) for l in r.items], "total": r.total, "pagina": r.pagina, "tamano": r.tamano,
        "atribuciones": [{"fuente": a.fuente, "texto": a.texto, "url": a.url} for a in r.atribuciones],
    }


@router.get("/busquedas")
def listar_busquedas(request: Request, tenant_id: UUID = Depends(tenant_actual)):
    return {"items": [
        {"id": str(b.id), "creada_en": b.creada_en.isoformat(), "estado": b.estado, "pais": b.pais,
         "departamento": b.departamento, "ciudad": b.ciudad, "total_leads": b.total_leads}
        for b in _repo(request, tenant_id).listar_busquedas()]}


@router.get("/busquedas/{busqueda_id}/leads")
def listar_leads(
    busqueda_id: UUID, request: Request,
    pagina: Annotated[int, Query(ge=1, le=100_000)] = 1,
    tamano: Annotated[int, Query(ge=1, le=TAMANO_MAXIMO)] = 25,
    tenant_id: UUID = Depends(tenant_actual),
):
    r = _repo(request, tenant_id).listar_leads(busqueda_id, pagina, tamano)
    if r is None:  # inexistente o de otro tenant: la misma respuesta
        raise HTTPException(status_code=404, detail="no_encontrada")
    return _cuerpo(r)


@router.get("/leads")
def listar_leads_de_fuente(
    request: Request,
    fuente: Annotated[str | None, Query(max_length=80)] = None,
    pagina: Annotated[int, Query(ge=1, le=100_000)] = 1,
    tamano: Annotated[int, Query(ge=1, le=TAMANO_MAXIMO)] = 25,
    tenant_id: UUID = Depends(tenant_actual),
):
    """Los leads de una fuente en todas las búsquedas del tenant (el tablero enlaza acá); sin `fuente`, todos."""
    if fuente is not None and fuente not in _fuentes_conocidas(request):
        return JSONResponse(status_code=422, content={"errores": [{"campo": "fuente", "codigo": "desconocida"}]})
    return _cuerpo(_repo(request, tenant_id).listar_leads_de_fuente(fuente, pagina, tamano))
