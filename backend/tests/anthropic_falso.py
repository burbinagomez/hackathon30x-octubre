"""Messages API de Anthropic falsa: httpx.MockTransport que captura los requests. Nunca red, key falsa."""
import json
from decimal import Decimal
from uuid import uuid4

import httpx

from evals.jueces.claude import JuezClaude

MODELO = "claude-sonnet-5-5"
# Misma forma que tarifas.yaml (llm.<modelo>), en USD por millón de tokens.
TARIFA = {"in_usd_por_M": Decimal("2.00"), "out_usd_por_M": Decimal("10.00")}
USO = {"input_tokens": 120, "output_tokens": 30}
CASO = {"id": "c1", "nombre": "Ferretería Sintética SAS", "pais": "CO", "icp": "ferreterías en Bogotá"}


def respuesta(entrada: dict, uso: dict = USO) -> dict:
    return {
        "id": "msg_falso", "type": "message", "role": "assistant", "model": MODELO,
        "content": [{"type": "tool_use", "id": "toolu_falso", "name": "veredicto", "input": entrada}],
        "stop_reason": "tool_use", "stop_sequence": None, "usage": uso,
    }


def cliente(capturados: list, entrada: dict | None = None) -> httpx.Client:
    """Cliente con transporte falso. Cada request a POST /v1/messages queda en `capturados` (cuerpo JSON)."""
    entrada = {"probabilidad": 0.8, "razon": "encaja"} if entrada is None else entrada

    def responder(request: httpx.Request) -> httpx.Response:
        if (request.method, request.url.path) != ("POST", "/v1/messages"):
            return httpx.Response(404)  # fuera del endpoint no se captura: el test lo ve como 0 requests
        capturados.append(json.loads(request.content))
        return httpx.Response(200, json=respuesta(entrada))

    return httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(responder),
                        headers={"x-api-key": "falsa-no-real", "anthropic-version": "2023-06-01"})


def juez(registro_costos, capturados: list, entrada: dict | None = None, prompt: str = "prompt de prueba",
         lote_id=None) -> JuezClaude:
    return JuezClaude(registro_costos=registro_costos, tarifa=TARIFA, modelo=MODELO, prompt=prompt,
                      lote_id=lote_id or uuid4(), http_client=cliente(capturados, entrada))
