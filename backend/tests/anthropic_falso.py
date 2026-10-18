"""Messages API de Anthropic falsa: httpx.MockTransport que captura los requests. Nunca red, key falsa."""
import json
from decimal import Decimal
from uuid import uuid4

import httpx

from evals.jueces.claude import JuezClaude

MODELO = "claude-sonnet-5-5"
CLAVE_FALSA = "sk-ant-test-XXXX"
# Misma forma que tarifas.yaml (llm.<modelo>), en USD por millón de tokens.
TARIFA = {"in_usd_por_M": Decimal("2.00"), "out_usd_por_M": Decimal("10.00")}
USO = {"input_tokens": 120, "output_tokens": 30}
# icp como dict: la forma que manda run.py (`| {"icp": datos["icp"]}`).
CASO = {"id": "c1", "nombre": "Ferretería Sintética SAS", "pais": "CO",
        "icp": {"pais": "CO", "ciiu": ["4752"], "descripcion": "Ferreterías con local propio"}}
SIN_TOOL_USE = {"content": [{"type": "text", "text": "La empresa parece encajar"}], "stop_reason": "max_tokens"}


def respuesta(entrada: dict | None = None, uso: dict = USO, content: list | None = None,
              stop_reason: str = "tool_use") -> dict:
    """Cuerpo de la Messages API. `content` propio pisa el bloque tool_use armado con `entrada`."""
    if content is None:
        content = [{"type": "tool_use", "id": "toolu_falso", "name": "veredicto", "input": entrada}]
    return {"id": "msg_falso", "type": "message", "role": "assistant", "model": MODELO, "content": content,
            "stop_reason": stop_reason, "stop_sequence": None, "usage": uso}


def transporte(capturados: list, entrada: dict | None = None, cabeceras: list | None = None,
               http: httpx.Response | None = None, **cuerpo) -> httpx.MockTransport:
    """Messages API falsa. Cada request a POST /v1/messages deja su cuerpo JSON en `capturados` y
    `dict(request.headers)` en `cabeceras`. `http` reemplaza la respuesta entera (p. ej. un 401);
    `cuerpo` va a `respuesta()` (content, stop_reason).
    """
    entrada = {"probabilidad": 0.8, "razon": "encaja"} if entrada is None else entrada

    def responder(request: httpx.Request) -> httpx.Response:
        if (request.method, request.url.path) != ("POST", "/v1/messages"):
            return httpx.Response(404)  # fuera del endpoint no se captura: el test lo ve como 0 requests
        capturados.append(json.loads(request.content))
        if cabeceras is not None:
            cabeceras.append(dict(request.headers))
        return http if http is not None else httpx.Response(200, json=respuesta(entrada, **cuerpo))

    return httpx.MockTransport(responder)


def cliente(capturados: list, entrada: dict | None = None, **kw) -> httpx.Client:
    """Cliente con transporte falso, sin headers propios: la key y la versión las pone el juez."""
    return httpx.Client(base_url="https://api.anthropic.com", transport=transporte(capturados, entrada, **kw))


def juez(registro_costos, capturados: list, entrada: dict | None = None, prompt: str = "prompt de prueba",
         lote_id=None, tarifa: dict = TARIFA, **kw) -> JuezClaude:
    return JuezClaude(registro_costos=registro_costos, tarifa=tarifa, modelo=MODELO, prompt=prompt,
                      lote_id=lote_id or uuid4(), api_key=CLAVE_FALSA, http_client=cliente(capturados, entrada, **kw))
