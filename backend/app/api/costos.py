"""GET /costos: el libro de costos, solo lectura. El tenant sale SIEMPRE de `tenant_actual`.

El lead va como booleano: ni su id ni ningún dato suyo salen por acá.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.sesion import tenant_actual
from app.modulos.costos.infraestructura.repositorio_libro import FilaLibro, leer_libro

router = APIRouter()


def _item(f: FilaLibro) -> dict:
    # Decimal como string (sin pasar por float). lote_id = busqueda_id.
    lote = None if f.lote_id is None else str(f.lote_id)
    return {
        "ts": f.ts.isoformat(), "tipo": f.tipo, "fuente": f.fuente, "proveedor": f.proveedor, "cantidad": str(f.cantidad),
        "costo_usd": str(f.costo_usd), "gratis": f.gratis, "busqueda_id": lote, "lote_id": lote, "lead": f.con_lead,
    }


@router.get("/costos")
def listar_costos(
    request: Request,
    pagina: Annotated[int, Query(ge=1, le=100_000)] = 1,
    busqueda_id: UUID | None = None,
    tenant_id: UUID = Depends(tenant_actual),
):
    r = leer_libro(request.app.state.engine, tenant_id, pagina, busqueda_id)
    return {
        "items": [_item(f) for f in r.items], "total": r.total, "pagina": r.pagina, "tamano": r.tamano,
        "total_usd": str(r.total_usd), "total_real_usd": str(r.total_real_usd),
        "por_tipo": [{"tipo": t, "costo_usd": str(v)} for t, v in r.por_tipo],
        "por_fuente": [{"fuente": f, "costo_usd": str(v)} for f, v in r.por_fuente],
    }
