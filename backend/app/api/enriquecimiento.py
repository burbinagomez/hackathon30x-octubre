"""Enriquecimiento de la 006 (sitio web, RUES, jev) en segundo plano, en paralelo al descubrimiento.

`ejecutar` lo arranca al terminar; POST /busquedas/{id}/enriquecer lo (re)arranca sin bloquear y GET
/busquedas/{id}/enriquecimiento da el progreso. Mismo caso de uso que la CLI, por tandas. Solo conteos: el contacto nunca sale.
El registro de lo que corre vive en memoria (app.state): tras un reinicio el GET recalcula desde la base.
"""
import logging
import threading
from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.sesion import tenant_actual
from app.composicion import adaptadores_enriquecer, buscador_sitio_web
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from app.modulos.enriquecimiento.aplicacion.enriquecer_lead import EnriquecerLead

router = APIRouter()
log = logging.getLogger(__name__)
# Cada tanda cabe en un presupuesto de tiempo; lo que no entra queda pendiente y lo toma la tanda siguiente.
TANDA = 15
MAX_HILOS = 8
PRESUPUESTO_S = 60.0
_LOCK_CREACION = threading.Lock()


def tanda(estado, tenant_id: UUID, busqueda_id: UUID):
    """Una tanda con su propia conexión y tenant (RLS por SET LOCAL en cada unidad de trabajo)."""
    repo = RepositorioLeadsPostgres(estado.engine, tenant_id, estado.cifrador)
    costos = PostgresCostos(estado.engine, tenant_id)
    extra = {"resolver": estado.resolver_dns} if getattr(estado, "resolver_dns", None) else {}
    verificador, enriquecedor, clasificador = adaptadores_enriquecer(estado.settings, costos, estado.tarifas, estado.transporte_http, **extra)
    buscador = buscador_sitio_web(costos, estado.tarifas, estado.transporte_http, **extra)
    caso = EnriquecerLead(repo, verificador, enriquecedor, clasificador, buscador=buscador, max_hilos=MAX_HILOS)
    return caso.ejecutar(busqueda_id, TANDA, PRESUPUESTO_S)


def _lanzar_en_hilo(trabajo: Callable[[], None]) -> None:
    threading.Thread(target=trabajo, daemon=True, name="enriquecimiento").start()


def _registro(estado) -> tuple[dict, threading.Lock]:
    with _LOCK_CREACION:
        if not hasattr(estado, "enriquecimientos"):
            estado.enriquecimientos = {}
            estado.enriquecimientos_lock = threading.Lock()
    return estado.enriquecimientos, estado.enriquecimientos_lock


def _correr(estado, tenant_id: UUID, busqueda_id: UUID, clave: tuple, registro: dict, lock: threading.Lock) -> None:
    hacer_tanda = getattr(estado, "tanda_enriquecimiento", tanda)
    try:
        while True:
            r = hacer_tanda(estado, tenant_id, busqueda_id)
            with lock:
                e = registro[clave]
                e["procesados"] += r.procesados
                e["contactables"] += r.contactables
                e["pendientes"] = r.pendientes
            if r.pendientes == 0:
                break
            if r.procesados == 0:  # sin avance (p. ej. cupo de una fuente agotado): seguir solo repetiría
                with lock:
                    registro[clave]["error"] = "sin_avance"
                break
    except Exception as exc:  # noqa: BLE001  nunca tira la api; solo el código, jamás el mensaje (puede traer datos)
        log.warning("enriquecimiento detenido: %s", type(exc).__name__)
        with lock:
            registro[clave]["error"] = "error_tanda"
    finally:
        with lock:
            registro[clave]["en_curso"] = False


def iniciar(estado, tenant_id: UUID, busqueda_id: UUID) -> dict:
    """Arranca el enriquecimiento si no corre ya para esa búsqueda. Devuelve el estado actual. No bloquea."""
    registro, lock = _registro(estado)
    clave = (tenant_id, busqueda_id)
    with lock:
        actual = registro.get(clave)
        if actual is not None and actual["en_curso"]:
            return dict(actual)
        registro[clave] = {"en_curso": True, "procesados": 0, "contactables": 0, "pendientes": None, "error": None}
        nuevo = dict(registro[clave])
    lanzador = getattr(estado, "lanzador_enriquecimiento", _lanzar_en_hilo)
    try:
        lanzador(lambda: _correr(estado, tenant_id, busqueda_id, clave, registro, lock))
    except Exception:  # noqa: BLE001
        with lock:
            registro[clave].update(en_curso=False, error="error_tanda")
        nuevo = dict(registro[clave])
    return nuevo


def _vista(estado, tenant_id: UUID, busqueda_id: UUID, interno: dict | None) -> dict:
    total, pendientes, con_contacto = RepositorioLeadsPostgres(
        estado.engine, tenant_id, estado.cifrador).conteos_enriquecimiento(busqueda_id)
    if interno is None:
        return {"en_curso": False, "procesados": total - pendientes, "contactables": con_contacto,
                "pendientes": pendientes, "total": total, "error": None}
    return {"en_curso": interno["en_curso"], "procesados": total - pendientes, "contactables": con_contacto,
            "pendientes": pendientes, "total": total, "error": interno["error"]}


def _existe(request: Request, tenant_id: UUID, busqueda_id: UUID) -> None:
    e = request.app.state
    if RepositorioLeadsPostgres(e.engine, tenant_id, e.cifrador).estado(busqueda_id) is None:
        raise HTTPException(status_code=404, detail="no_encontrada")  # inexistente o de otro tenant (RLS)


@router.post("/busquedas/{busqueda_id}/enriquecer", status_code=202)
def enriquecer(busqueda_id: UUID, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    _existe(request, tenant_id, busqueda_id)
    interno = iniciar(request.app.state, tenant_id, busqueda_id)
    return _vista(request.app.state, tenant_id, busqueda_id, interno)


@router.get("/busquedas/{busqueda_id}/enriquecimiento")
def progreso(busqueda_id: UUID, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    _existe(request, tenant_id, busqueda_id)
    registro, lock = _registro(request.app.state)
    with lock:
        interno = registro.get((tenant_id, busqueda_id))
        interno = dict(interno) if interno else None
    return _vista(request.app.state, tenant_id, busqueda_id, interno)
