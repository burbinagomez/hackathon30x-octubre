"""clasificador_openrouter: el mismo puerto que JevClasificador (¿el lead encaja con el ICP?), contra OpenRouter
(/chat/completions con tool calling forzado, la forma del InterpretadorOpenRouter de la Puerta B).

Reusa de jev las instrucciones (encaje_jev_v1.json) y el bloque de datos con su escape: actividad, nombre y ciudad,
nunca contacto. A diferencia de Jev, nunca lanza: error, timeout, 4xx/5xx o salida inválida devuelven 'ninguna' y el
enriquecimiento sigue. Costos (llm_tokens_in/out, proveedor openrouter) antes de devolver; sin uso legible se cobra el
techo. No loguea el nombre del lead ni la key; no hay logs en este módulo a propósito.
"""
import json
from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.enriquecimiento.dominio.puertos import Encaje
from app.modulos.enriquecimiento.infraestructura.adaptadores.jev_clasificador import (
    ETIQUETAS,
    PROMPT,
    bloque_de_datos,
)

TIMEOUT_S = 10.0
MAX_TOKENS = 128
TOKENS_OCULTOS = 1024  # lo que el proveedor suma al prompt (herramientas, plantilla): el techo no se queda corto
HERRAMIENTA = "clasificar_encaje"
NO_ENVIADO = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
NINGUNA = Encaje("ninguna", 0.0)
FUNCION = {"type": "function", "function": {
    "name": HERRAMIENTA, "description": "Devuelve si el lead encaja con el ICP.",
    "parameters": {"type": "object", "required": ["encaje"], "additionalProperties": False, "properties": {
        "encaje": {"type": "string", "enum": ["encaja", "no_encaja", "ninguna"]},
        "probabilidad": {"type": "number", "minimum": 0, "maximum": 1}}}}}
SUFIJO = f"\n\nRespondé llamando a la herramienta {HERRAMIENTA}: el campo encaje lleva la etiqueta."


class ClasificadorOpenRouter:
    def __init__(self, registro_costos: RegistroCostos, tarifa: dict, modelo: str, api_key: str,
                 http_client: httpx.Client):
        self._costos, self._tarifa, self._modelo = registro_costos, tarifa, modelo
        self._api_key, self._http = api_key, http_client

    def __repr__(self) -> str:  # sin la key
        return "ClasificadorOpenRouter()"

    def clasificar(self, lead_id: UUID, descripcion_icp: str, nombre: str, ciudad: str | None,
                   actividad: str | None) -> Encaje:
        cuerpo = json.dumps({
            "model": self._modelo, "max_tokens": MAX_TOKENS, "temperature": 0,
            "messages": [{"role": "system", "content": PROMPT["instrucciones"] + SUFIJO},
                         {"role": "user", "content": bloque_de_datos(descripcion_icp, nombre, ciudad, actividad)}],
            "tools": [FUNCION], "tool_choice": {"type": "function", "function": {"name": HERRAMIENTA}},
        }, ensure_ascii=False).encode("utf-8")
        techo = {"in": len(cuerpo) + TOKENS_OCULTOS, "out": MAX_TOKENS}
        try:
            r = self._http.post("/chat/completions", content=cuerpo, timeout=TIMEOUT_S, headers={
                "Authorization": f"Bearer {self._api_key}", "content-type": "application/json"})
        except NO_ENVIADO:
            return NINGUNA  # no salió: no se factura
        except httpx.HTTPError:
            self._registrar(techo, lead_id)  # salió y se cortó: pudo facturarse
            return NINGUNA
        if r.is_error:
            return NINGUNA  # el proveedor rechazó sin procesar
        try:
            datos = r.json()
        except ValueError:
            datos = None
        uso = datos.get("usage") if isinstance(datos, dict) else None
        leido = None
        if isinstance(uso, dict) and all(type(uso.get(k)) is int and uso[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
            leido = {"in": uso["prompt_tokens"], "out": uso["completion_tokens"]}
        self._registrar(leido or techo, lead_id)  # antes de validar: los tokens se gastaron igual
        return self._encaje(datos)

    @staticmethod
    def _encaje(datos) -> Encaje:
        try:
            args = [c["function"]["arguments"] for c in datos["choices"][0]["message"]["tool_calls"]
                    if c.get("function", {}).get("name") == HERRAMIENTA]
            if len(args) != 1:
                return NINGUNA
            salida = json.loads(args[0]) if isinstance(args[0], str) else args[0]
            etiqueta = salida["encaje"]
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            return NINGUNA
        if etiqueta not in ETIQUETAS:
            return NINGUNA
        p = salida.get("probabilidad")
        valida = isinstance(p, (int, float)) and not isinstance(p, bool) and 0 <= p <= 1
        return Encaje(etiqueta, float(p) if valida else 0.0)

    def _registrar(self, uso: dict, lead_id: UUID) -> None:
        for tipo, clave, tarifa in (("llm_tokens_in", "in", "in_usd_por_M"), ("llm_tokens_out", "out", "out_usd_por_M")):
            self._costos.registrar(OperacionCosto(
                tipo=tipo, unidades=Decimal(uso[clave]), costo_unitario=Decimal(self._tarifa[tarifa]) / 1_000_000,
                moneda="USD", proveedor="openrouter", fuente=None, canal=None, lead_id=lead_id, lote_id=None,
                gratis=False))
