"""JuezClaude: Messages API de Anthropic con httpx directo (sin SDK) y salida forzada por tool_use.

La key llega por constructor (la lee la composición desde `entorno`); el juez nunca lee el entorno ni la
muestra: sin __repr__ propio, sin logs, y las excepciones no la llevan en el mensaje.
"""
import json
from decimal import Decimal
from uuid import UUID

import httpx

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from evals.jueces.puerto import SalidaJuezInvalida, Veredicto
from evals.scorers import forma

VERSION_API = "2023-06-01"
MAX_TOKENS = 512
HERRAMIENTA = {
    "name": "veredicto",
    "description": "Devuelve la probabilidad de que el caso cumpla la tarea y una razón corta.",
    "input_schema": {
        "type": "object",
        "properties": {"probabilidad": {"type": "number", "minimum": 0, "maximum": 1},
                       "razon": {"type": "string"}},
        "required": ["probabilidad", "razon"],
    },
}


def _bloque_caso(caso: dict) -> str:
    # JSON por clave (nunca por posición) y sin '<'/'>' crudos: un campo no puede abrir ni cerrar el bloque.
    datos = json.dumps(caso, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e")
    return f"<caso>{datos}</caso>"


class JuezClaude:
    determinista_si_se_demuestra = False

    def __init__(self, registro_costos: RegistroCostos, tarifa: dict, modelo: str, prompt: str,
                 lote_id: UUID, api_key: str, http_client: httpx.Client):
        self._costos = registro_costos
        self._tarifa, self._modelo, self._prompt = tarifa, modelo, prompt
        self._lote_id, self._api_key, self._http = lote_id, api_key, http_client

    def juzgar(self, tarea: str, caso: dict) -> Veredicto:
        r = self._http.post("/v1/messages", headers={"x-api-key": self._api_key, "anthropic-version": VERSION_API},
                            json={"model": self._modelo, "max_tokens": MAX_TOKENS, "temperature": 0,
                                  "system": self._prompt, "tools": [HERRAMIENTA],
                                  "tool_choice": {"type": "tool", "name": HERRAMIENTA["name"]},
                                  "messages": [{"role": "user", "content": f"Tarea: {tarea}\n{_bloque_caso(caso)}"}]})
        r.raise_for_status()  # 4xx/5xx: httpx.HTTPStatusError, sin usage y sin filas de costo
        cuerpo = r.json()
        self._registrar(cuerpo.get("usage") or {})  # antes de validar: los tokens se gastaron igual
        return self._veredicto(cuerpo)

    def _registrar(self, uso: dict) -> None:
        for tipo, clave, tarifa in (("llm_tokens_in", "input_tokens", "in_usd_por_M"),
                                    ("llm_tokens_out", "output_tokens", "out_usd_por_M")):
            self._costos.registrar(OperacionCosto(
                tipo=tipo, unidades=Decimal(int(uso.get(clave, 0))),
                costo_unitario=self._tarifa[tarifa] / 1_000_000,  # entero: USD por millón → por token, sin float
                moneda="USD", proveedor="anthropic", fuente="evals", canal=None, lead_id=None,
                lote_id=self._lote_id, gratis=False))

    @staticmethod
    def _veredicto(cuerpo: dict) -> Veredicto:
        entradas = [b.get("input") for b in cuerpo.get("content") or []
                    if b.get("type") == "tool_use" and b.get("name") == HERRAMIENTA["name"]]
        if len(entradas) != 1 or not isinstance(entradas[0], dict):
            raise SalidaJuezInvalida(f"sin tool_use (stop_reason={cuerpo.get('stop_reason')})")
        salida = entradas[0]
        if regla := forma.encaje(salida):
            raise SalidaJuezInvalida(f"forma:{regla}")
        if not isinstance(salida.get("razon"), str):
            raise SalidaJuezInvalida("forma:razon")
        return Veredicto(float(salida["probabilidad"]), salida["razon"])
