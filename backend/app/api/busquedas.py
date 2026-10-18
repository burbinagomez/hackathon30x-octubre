"""Nueva búsqueda: vista previa (crea el borrador) y ejecutar. El tenant sale SIEMPRE de `tenant_actual`, nunca del body.

Repo y libro de costos se arman por request con el tenant del token; el transporte HTTP y las actividades se leen de
`app.state` en cada request, no al arrancar.
"""
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.canales import canal_habilitado
from app.api.sesion import tenant_actual
from app.composicion import fabrica_de_fuentes
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBorrador
from app.modulos.descubrimiento.aplicacion.registro import actividades_de
from app.modulos.descubrimiento.aplicacion.vista_previa import VistaPrevia
from app.modulos.descubrimiento.dominio.errores import (
    BusquedaNoEncontrada,
    BusquedaYaEjecutada,
    CriterioNoSoportado,
    FuenteNoDisponible,
    LimiteFuenteAgotado,
)
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres

router = APIRouter()

Palabra = Annotated[str, StringConstraints(min_length=1, max_length=40)]


class PedidoVistaPrevia(BaseModel):
    model_config = ConfigDict(extra="forbid")  # un tenant_id en el body es un 422, no un campo ignorado

    pais: Literal["CO", "MX", "PE", "BR"]
    ciiu: Annotated[str, StringConstraints(pattern=r"^\d{4}$")]
    departamento: Annotated[str, StringConstraints(max_length=80)] | None = None
    ciudad: Annotated[str, StringConstraints(max_length=80)] | None = None
    ingresos_min: int | None = Field(default=None, ge=0)
    palabras_clave: list[Palabra] = Field(default_factory=list, max_length=10)
    exclusiones: list[Palabra] = Field(default_factory=list, max_length=10)
    canal_preferido: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    tope_gasto_usd: Decimal = Field(gt=0)  # TOPE_MAXIMO_USD: Pulido, junto con el tope
    mensaje_base: Annotated[str, StringConstraints(max_length=1000)] = ""


def _criterios(p: PedidoVistaPrevia) -> CriteriosICP:
    filtros: dict[str, str | tuple[str, ...]] = {"ciiu": p.ciiu}
    for clave in ("departamento", "ciudad"):
        if getattr(p, clave):
            filtros[clave] = getattr(p, clave)
    if p.ingresos_min is not None:
        filtros["ingresos_min"] = str(p.ingresos_min)
    # Se guardan, pero ninguna fuente las aplica todavía (T022-T023, Pulido): salen como ignoradas, no en silencio.
    if p.palabras_clave:
        filtros["palabras_clave"] = tuple(p.palabras_clave)
    if p.exclusiones:
        filtros["exclusiones"] = tuple(p.exclusiones)
    return CriteriosICP(p.pais, filtros)


def _repo(request: Request, tenant_id: UUID) -> RepositorioLeadsPostgres:
    estado = request.app.state
    return RepositorioLeadsPostgres(estado.engine, tenant_id, estado.cifrador)


def _fabrica(request: Request, tenant_id: UUID):
    estado = request.app.state
    return fabrica_de_fuentes(
        estado.registro, ajustes=lambda: estado.settings, costos=PostgresCostos(estado.engine, tenant_id),
        tarifas=estado.tarifas, limites={}, api_key=None, camaras_yaml=lambda: request.app.state.camaras_yaml,
        transporte=lambda: request.app.state.transporte_http,  # se lee al armar cada fuente, en cada request
    )


@router.post("/busquedas/vista-previa", status_code=201)
def vista_previa(pedido: PedidoVistaPrevia, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    errores = []
    if pedido.departamento is not None and pedido.departamento not in request.app.state.departamentos_yaml.get(pedido.pais, {}):
        errores.append({"campo": "departamento", "codigo": "desconocido"})  # no es un código DIVIPOLA de ese país
    if not canal_habilitado(pedido.canal_preferido, request.app.state.canales_contacto):
        errores.append({"campo": "canal_preferido", "codigo": "canal_no_habilitado"})
    if errores:
        return JSONResponse(status_code=422, content={"errores": errores})
    caso = VistaPrevia(_repo(request, tenant_id), _fabrica(request, tenant_id),
                       actividades_de(request.app.state.actividades_yaml))
    r = caso.ejecutar(_criterios(pedido), pedido.canal_preferido, pedido.tope_gasto_usd, pedido.mensaje_base)
    # [MIN]: sin `contar` no hay conteo ni costo, y el tope no se aplica: todo eso va null, nunca 0 ni true.
    return {
        "busqueda_id": str(r.busqueda_id),
        "fuentes": [{"fuente": f.clave, "conteo": None, "motivo": "sin_conteo", "ignorados": list(f.ignorados),
                     "truncado": False} for f in r.fuentes],
        "descartadas": [{"fuente": clave, "motivo": motivo} for clave, motivo in r.descartadas.items()],
        "costo_vista_previa_usd": None, "costo_estimado_usd": None, "costo_maximo_usd": None,
        "creditos_restantes_mes": None, "requests_restantes_24h": None, "dentro_del_tope": None,
    }


_MOTIVO_DE_ERROR = {FuenteNoDisponible: "no_disponible", LimiteFuenteAgotado: "limite_agotado",
                    CriterioNoSoportado: "criterio_no_soportado"}


@router.post("/busquedas/{busqueda_id}/ejecutar")
def ejecutar(busqueda_id: UUID, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    repo = _repo(request, tenant_id)
    caso = EjecutarBorrador(repo, _fabrica(request, tenant_id), actividades_de(request.app.state.actividades_yaml))
    try:
        r = caso.ejecutar(busqueda_id)
    except BusquedaNoEncontrada:  # inexistente o de otro tenant: la misma respuesta
        raise HTTPException(status_code=404, detail="no_encontrada") from None
    except BusquedaYaEjecutada:
        raise HTTPException(status_code=409, detail="ya_ejecutada") from None
    return {
        "busqueda_id": str(r.busqueda_id),
        "estado": repo.estado(r.busqueda_id),
        "encontrados": r.encontrados, "unicos": r.unicos, "nuevos": r.nuevos,
        "errores": [{"fuente": clave, "motivo": _MOTIVO_DE_ERROR.get(type(e), "error")} for clave, e in r.errores.items()],
        "sin_fuente_para": None if r.sin_fuente_para is None else {
            "pais": r.sin_fuente_para[0], "filtros": {k: list(v) if isinstance(v, tuple) else v
                                                      for k, v in r.sin_fuente_para[1].items()}},
    }
