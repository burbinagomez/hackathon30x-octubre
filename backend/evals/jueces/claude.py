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
from evals.jueces.puerto import ErrorJuez, SalidaJuezInvalida, Veredicto
from evals.scorers import forma

VERSION_API = "2023-06-01"
MAX_TOKENS = 512
# Margen sobre los ~346 tokens del system prompt de tool use que la API agrega sin que viajen en el body.
TOKENS_OCULTOS = 1024
# Fallas de transporte en que el request nunca salió: sin fila de costo.
NO_ENVIADO = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
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
        body = json.dumps({"model": self._modelo, "max_tokens": MAX_TOKENS, "temperature": 0,
                           "system": self._prompt, "tools": [HERRAMIENTA],
                           "tool_choice": {"type": "tool", "name": HERRAMIENTA["name"]},
                           "messages": [{"role": "user", "content": f"Tarea: {tarea}\n{_bloque_caso(caso)}"}]},
                          ensure_ascii=False).encode("utf-8")
        # Techo de la llamada, para cuando salió y no se puede leer el usage: un token nunca ocupa menos de un
        # byte del body, más los tokens que la API suma sin que viajen (system prompt de tool use, ~346).
        techo = {"input_tokens": len(body) + TOKENS_OCULTOS, "output_tokens": MAX_TOKENS}
        # Los raise van FUERA del except: `from None` suprime la cadena al mostrarla pero igual setea __context__,
        # y la excepción de httpx lleva request.headers (la key) y response.text.
        codigo = None
        try:
            r = self._http.post("/v1/messages", content=body,
                                headers={"x-api-key": self._api_key, "anthropic-version": VERSION_API,
                                         "content-type": "application/json"})
            r.raise_for_status()  # 4xx/5xx: Anthropic no factura errores, sin filas
        except httpx.HTTPStatusError as e:
            codigo = f"http_{e.response.status_code}"
        except NO_ENVIADO:
            codigo = "red"  # el request no salió: nada que cobrar
        except httpx.HTTPError:
            codigo = "red"
            self._registrar(techo)  # salió y se cortó (ReadTimeout, RemoteProtocolError…): pudo facturarse
        if codigo:
            raise ErrorJuez(codigo)
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = None
        uso = cuerpo.get("usage") if isinstance(cuerpo, dict) else None
        # Antes de validar: los tokens se gastaron igual. Un 200 sin usage legible se cobra al techo.
        legible = isinstance(uso, dict) and all(isinstance(uso.get(k), int) for k in techo)
        self._registrar(uso if legible else techo)
        if not isinstance(cuerpo, dict):
            raise SalidaJuezInvalida("cuerpo_no_objeto")
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
