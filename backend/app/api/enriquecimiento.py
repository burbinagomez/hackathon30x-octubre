"""POST /busquedas/{id}/enriquecer: el enriquecimiento de la 006 (sitio web, RUES, jev) desde la pantalla, por tandas.

Mismo caso de uso que la CLI. La respuesta son solo conteos: el contacto nunca sale de la API.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.api.sesion import tenant_actual
from app.composicion import adaptadores_enriquecer, buscador_sitio_web
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from app.modulos.enriquecimiento.aplicacion.enriquecer_lead import EnriquecerLead

router = APIRouter()
# Por tanda: Cloudflare corta a los 100 s. Los leads de la tanda corren en paralelo (hasta MAX_HILOS) y la tanda tiene un
# presupuesto de tiempo: lo que no entra queda pendiente para "Seguir con los que quedan".
TANDA = 15
MAX_HILOS = 8
PRESUPUESTO_S = 60.0


@router.post("/busquedas/{busqueda_id}/enriquecer")
async def enriquecer(busqueda_id: UUID, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    e = request.app.state
    repo = RepositorioLeadsPostgres(e.engine, tenant_id, e.cifrador)
    if repo.estado(busqueda_id) is None:  # no existe o es de otro tenant (RLS): no se distingue
        raise HTTPException(status_code=404, detail="no_encontrada")
    costos = PostgresCostos(e.engine, tenant_id)
    extra = {"resolver": e.resolver_dns} if getattr(e, "resolver_dns", None) else {}
    verificador, enriquecedor, clasificador = adaptadores_enriquecer(e.settings, costos, e.tarifas, e.transporte_http, **extra)
    buscador = buscador_sitio_web(costos, e.tarifas, e.transporte_http, **extra)
    caso = EnriquecerLead(repo, verificador, enriquecedor, clasificador, buscador=buscador, max_hilos=MAX_HILOS)
    r = await run_in_threadpool(caso.ejecutar, busqueda_id, TANDA, PRESUPUESTO_S)
    return {"procesados": r.procesados, "contactables": r.contactables, "clasificados": r.clasificados,
            "sin_clasificar": r.sin_clasificar, "cortado": r.cortado, "pendientes": r.pendientes}
