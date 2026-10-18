"""Messages API falsa para la Puerta B (herramienta `sugerir_icp`): MockTransport que captura los requests. Sin red."""
import json

import httpx

MODELO = "claude-haiku-5-5"
CLAVE_FALSA = "sk-ant-test-INTAKE"
USO = {"input_tokens": 200, "output_tokens": 60}
VALIDA = {"pais": "CO", "ciiu": "4752", "departamento": "Antioquia", "ciudad": None, "ingresos_min": 500000000,
          "palabras_clave": ["ferretería"], "exclusiones": []}
SIN_PAIS = {k: v for k, v in VALIDA.items() if k != "pais"}
HERRAMIENTA = "sugerir_icp"


def respuesta(entrada: dict | None, uso: dict | None = USO, content: list | None = None) -> dict:
    if content is None:
        content = [{"type": "tool_use", "id": "toolu_falso", "name": HERRAMIENTA, "input": entrada}]
    cuerpo = {"id": "msg_falso", "type": "message", "role": "assistant", "model": MODELO, "content": content,
              "stop_reason": "tool_use", "stop_sequence": None}
    if uso is not None:
        cuerpo["usage"] = uso
    return cuerpo


def transporte(capturados: list, *respuestas, cabeceras: list | None = None) -> httpx.MockTransport:
    """Cada request a POST /v1/messages deja su cuerpo en `capturados`. `respuestas` se consumen en orden (la última se
    repite): un dict es el cuerpo de un 200, un `httpx.Response` va tal cual y una excepción se lanza."""
    pendientes = list(respuestas) or [respuesta(VALIDA)]

    def responder(request: httpx.Request) -> httpx.Response:
        if (request.method, request.url.path) != ("POST", "/v1/messages"):
            return httpx.Response(404)
        capturados.append(json.loads(request.content))
        if cabeceras is not None:
            cabeceras.append(dict(request.headers))
        r = pendientes.pop(0) if len(pendientes) > 1 else pendientes[0]
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, httpx.Response) else httpx.Response(200, json=r)

    return httpx.MockTransport(responder)


def cliente(capturados: list, *respuestas, cabeceras: list | None = None) -> httpx.Client:
    return httpx.Client(base_url="https://api.anthropic.com", transport=transporte(capturados, *respuestas, cabeceras=cabeceras))
