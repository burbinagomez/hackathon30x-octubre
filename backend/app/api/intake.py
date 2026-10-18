"""Intake: Puerta B (una frase -> ICP sugerido) y el estado de las puertas. El tenant sale SIEMPRE de `tenant_actual`.

Ninguna ruta crea una búsqueda: solo prellenan el formulario; la vista previa (`/busquedas/vista-previa`) es la que
congela criterios. Nunca se loguea la frase ni la respuesta del modelo; los errores salen como códigos.
"""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.sesion import tenant_actual
from app.composicion import generador_de_frase, ia_configurada
from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.aplicacion.registro import actividades_de
from app.modulos.intake.aplicacion.interpretar_frase import MAX_FRASE, MAX_TURNOS, InterpretarFrase
from app.modulos.intake.dominio.errores import ErrorGeneracion, FraseFueraDeRango, SalidaIntakeInvalida

router = APIRouter()

FUENTE_LOOKALIKE = "datos_gov_co_rues"  # la misma que usa POST /intake/lookalike


class Turno(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol: Literal["usuario", "asistente"]
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_FRASE)]


class PedidoFrase(BaseModel):
    model_config = ConfigDict(extra="forbid")  # un tenant_id en el body es un 422, no un campo ignorado

    frase: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_FRASE)]
    # Conversación previa (enmienda 2026-10-18): la IA pudo haber preguntado a quién le vende.
    historial: list[Turno] = Field(default_factory=list, max_length=MAX_TURNOS)


@router.get("/intake/estado")
def estado(request: Request):
    """Qué puertas están disponibles; el front oculta las que no. Lookalike = su fuente está conectada por config."""
    e = request.app.state
    return {"frase": ia_configurada(e.settings, e.tarifas_llm), "lookalike": FUENTE_LOOKALIKE in e.registro.fuentes}


@router.post("/intake/frase")
def frase(pedido: PedidoFrase, request: Request, tenant_id: UUID = Depends(tenant_actual)):
    e = request.app.state
    costos = PostgresCostos(e.engine, tenant_id)
    actividades = actividades_de(e.actividades_yaml)
    generador = generador_de_frase(e.settings, e.tarifas_llm, costos, e.transporte_http, codigos_ciiu=list(actividades))
    if generador is None:  # sin llamada, sin costo: la API sigue viva sin IA
        raise HTTPException(status_code=503, detail="ia_no_disponible")
    caso = InterpretarFrase(generador, costos, e.geografia, actividades)
    try:
        r = caso.ejecutar(pedido.frase, [(t.rol, t.texto) for t in pedido.historial])
    except FraseFueraDeRango:
        raise HTTPException(status_code=422, detail="frase_fuera_de_rango") from None
    except SalidaIntakeInvalida:
        raise HTTPException(status_code=502, detail="ia_salida_invalida") from None
    except ErrorGeneracion:
        raise HTTPException(status_code=502, detail="ia_error") from None
    return {"sugerencia": r.sugerencia.como_dict(), "pregunta": r.pregunta, "explicacion": r.explicacion,
            "ciiu_descartado": r.ciiu_descartado,
            "costo_usd": str(r.costo_usd)}
