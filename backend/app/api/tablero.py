from decimal import Decimal

from fastapi import APIRouter, Depends, Request

from app.api.sesion import tenant_actual
from app.modulos.tablero.infraestructura.persistencia.repositorio_tablero import FilaFuente, leer_tablero

router = APIRouter()


def _monto(valor: Decimal | None) -> str | None:
    # Decimal como string (sin pasar por float); null = "sin dato", nunca "0".
    return None if valor is None else str(valor)


def _fila(f: FilaFuente) -> dict:
    # Costo y CPL salen de `costos`; lo que todavía no se calcula va null ("sin dato"), nunca 0.
    return {
        "fuente": f.fuente, "encontrados": f.encontrados, "unicos": f.unicos, "icp": None,
        "costo_lista": _monto(f.costo_lista), "costo_real": _monto(f.costo_real),
        "desperdicio_lista": None, "desperdicio_real": None,
        "cpl_lista": _monto(f.cpl_lista), "cpl_real": _monto(f.cpl_real), "cuenta_naturales": False, "naturales_no_contactables": None,
        "enriquecidos": f.enriquecidos, "contactables": f.contactables, "con_telefono": f.con_telefono,
        "calificados": f.calificados,
    }


@router.get("/tablero/fuentes")
def tablero_fuentes(request: Request, tenant_id=Depends(tenant_actual)):
    datos = leer_tablero(request.app.state.engine, tenant_id)
    return {
        "fuentes": [_fila(f) for f in datos.fuentes],
        "total": _fila(datos.total),
        "costo_evals": _monto(datos.costo_evals),
        "costo_intake": _monto(datos.costo_intake),
        "cobertura": None,
        "revisiones_pendientes": None,
        "atribuciones": [{"fuente": a.fuente, "texto": a.texto, "url": a.url} for a in datos.atribuciones],
    }
