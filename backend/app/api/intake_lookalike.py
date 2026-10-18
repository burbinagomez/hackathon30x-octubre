"""Puerta A de intake ("ya me compran"): de una lista de nombres a una sugerencia de filtros para Nueva búsqueda.

El tenant sale SIEMPRE de `tenant_actual`. Los nombres pegados son insumo de la corrida: no se guardan ni se loguean;
vuelven a la pantalla del usuario solo los que no resolvieron. No crea búsquedas ni leads.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.sesion import tenant_actual
from app.composicion import armador_de_fuente
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.aplicacion.camaras import cargar_camaras
from app.modulos.descubrimiento.dominio.errores import FuenteNoDisponible
from app.modulos.intake.aplicacion.resolver_lookalike import ResolverLookalike
from app.modulos.intake.dominio.errores import IntakeFueraDeRango

router = APIRouter()

from app.api.intake import FUENTE_LOOKALIKE as CLAVE_FUENTE  # una sola fuente de verdad
Nombre = Annotated[str, StringConstraints(max_length=200)]


class PedidoLookalike(BaseModel):
    model_config = ConfigDict(extra="forbid")  # un tenant_id en el body es un 422

    # El tope duro es de abuso; el rango 5-50 lo decide el caso de uso (y responde con su propio código).
    nombres: list[Nombre] = Field(max_length=500)


def _camara_a_departamento(camaras_yaml) -> dict[str, str]:
    # ponytail: una cámara puede cubrir varios departamentos (la 04: Bogotá y Cundinamarca); gana el de menor código
    # (11, Bogotá, la sede). El dataset no trae municipio, así que no hay forma de afinarlo.
    return {codigo: min(c.departamentos) for codigo, c in cargar_camaras(camaras_yaml).items() if c.departamentos}


@router.post("/intake/lookalike")
def lookalike(pedido: PedidoLookalike, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    estado = request.app.state
    registrada = estado.registro.fuentes.get(CLAVE_FUENTE)
    if registrada is None:  # desconectada por config
        raise HTTPException(status_code=503, detail="lookalike_no_disponible")
    clase, meta = registrada
    costos = PostgresCostos(estado.engine, tenant_id)
    buscador = armador_de_fuente(
        clase, meta, ajustes=lambda: estado.settings, costos=costos, tarifas=estado.tarifas, limites=estado.limites,
        api_key=estado.settings.croma_api_key, transporte=lambda: estado.transporte_http,
        camaras_yaml=lambda: estado.camaras_yaml,
    )(None)  # sin lote propio: cada consulta lleva el de la corrida en su contexto de costo
    resolver = ResolverLookalike(
        buscador, _camara_a_departamento(estado.camaras_yaml), ciiu_validos={str(c) for c in estado.actividades_yaml}
    )
    try:
        r = resolver.ejecutar(pedido.nombres)
    except IntakeFueraDeRango:
        return JSONResponse(status_code=422, content={"errores": [{"campo": "nombres", "codigo": "fuera_de_rango"}]})
    except FuenteNoDisponible:  # solo la clase: el mensaje del error no sale
        raise HTTPException(status_code=503, detail="fuente_no_disponible") from None
    s = r.distribucion.sugerencia
    return {
        "sugerencia": {"pais": s.pais, "ciiu": s.ciiu, "departamento": s.departamento, "ciudad": s.ciudad,
                       "ingresos_min": s.ingresos_min, "palabras_clave": list(s.palabras_clave),
                       "exclusiones": list(s.exclusiones)},
        "explicacion": {"ciiu": [list(p) for p in r.distribucion.ciiu],
                        "departamento": [list(p) for p in r.distribucion.departamento]},
        "resueltos": r.resueltos,
        "no_resueltos": r.no_resueltos,
        "costo_usd": str(costos.gasto_busqueda(r.lote_id)),
    }
