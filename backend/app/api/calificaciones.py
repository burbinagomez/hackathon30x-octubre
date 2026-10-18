from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.sesion import tenant_actual
from app.modulos.calificacion.aplicacion.importar_calificaciones import ImportarCalificaciones
from app.modulos.calificacion.dominio.errores import ArchivoInvalido, TarifaPendiente
from app.modulos.calificacion.infraestructura.persistencia.postgres_calificaciones import PostgresCalificaciones
from app.modulos.calificacion.infraestructura.persistencia.repositorio_cpql import FilaCPQL, leer_cpql

router = APIRouter()
LIMITE_BYTES = 1024 * 1024  # plan.md: ≤ 1 MB, cortado mientras llega el cuerpo, antes del adaptador


def _codigo(status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"codigo": codigo})


def _monto(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor)  # Decimal como string; null = "sin dato", nunca "0"


def _fila(f: FilaCPQL) -> dict:
    return {"fuente": f.fuente, "costo_lista": _monto(f.costo_lista), "costo_real": _monto(f.costo_real),
            "calificados": f.calificados, "cpql_lista": _monto(f.cpql_lista), "cpql_real": _monto(f.cpql_real)}


@router.post("/calificaciones/importar")
async def importar(request: Request, tenant_id=Depends(tenant_actual)):
    if request.headers.get("content-type", "").split(";")[0].strip() != "text/csv":
        return _codigo(415, "tipo_no_soportado")
    calificador = request.app.state.calificador
    if calificador is None:
        return _codigo(503, "calificador_deshabilitado")
    cuerpo = bytearray()
    async for trozo in request.stream():
        cuerpo += trozo
        if len(cuerpo) > LIMITE_BYTES:
            return _codigo(413, "archivo_muy_grande")

    caso = ImportarCalificaciones(calificador, PostgresCalificaciones(request.app.state.engine, tenant_id),
                                  request.app.state.tarifas.get("dapta"))
    try:
        r = await run_in_threadpool(caso.ejecutar, bytes(cuerpo))
    except TarifaPendiente:
        return _codigo(409, "tarifa_pendiente")
    except ArchivoInvalido:
        return _codigo(422, "archivo_invalido")
    return {"importadas": r.importadas, "duplicadas": r.duplicadas, "conflictos": r.conflictos,
            "no_cumple": r.no_cumple, "ref_desconocida": r.ref_desconocida,
            "rechazadas": [{"fila": f.fila, "motivo": f.motivo} for f in r.rechazadas]}


@router.get("/calificaciones/cpql")
def cpql(request: Request, tenant_id=Depends(tenant_actual)):
    filas, total = leer_cpql(request.app.state.engine, tenant_id)
    return {"fuentes": [_fila(f) for f in filas], "total": _fila(total) if total else None}
