"""jev_clasificador: pregunta a jev si el lead encaja con el ICP.

Defensas: los datos del lead van como JSON dentro de un bloque delimitado, con < y > escapados (un nombre no
abre ni cierra el bloque); las instrucciones salen de encaje_jev_v1.json, nunca del lead. El costo se registra
con los tokens que informa jev, antes de validar la salida: una salida rota también se paga. Un 200 sin uso
legible (no es JSON, o falta tokens_in válido) se cobra al techo, los bytes del body enviado, como JuezClaude.
Una falla HTTP también deja fila: 500/502/503 en 0, 504 o timeout propio al techo, y lanza JevNoDisponible.
"""
import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
from pydantic import SecretStr

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.enriquecimiento.dominio.errores import JevNoDisponible, SalidaJevInvalida, UsoJevInvalido
from app.modulos.enriquecimiento.dominio.puertos import Encaje

PROMPT = json.loads((Path(__file__).parent / "encaje_jev_v1.json").read_text(encoding="utf-8"))
TIMEOUT_S = 30.0
ETIQUETAS = {"encaja", "no_encaja", "ninguna"}
SIN_JSON = object()
NO_PROCESO = {500, 502, 503}


def bloque_de_datos(descripcion_icp: str, nombre: str, ciudad: str | None, actividad: str | None) -> str:
    datos = json.dumps({"actividad_declarada": actividad, "nombre_negocio": nombre, "ciudad": ciudad,
                        "descripcion_icp": descripcion_icp}, ensure_ascii=False)
    datos = datos.replace("<", "\\u003c").replace(">", "\\u003e")  # escape JSON válido: json.loads devuelve el texto
    return f"<datos_del_lead>\n{datos}\n</datos_del_lead>"


def cuerpo_jev(descripcion_icp: str, nombre: str, ciudad: str | None, actividad: str | None) -> bytes:
    """Bytes exactos del body: su largo es el techo de tokens cuando jev no informa un uso legible."""
    return json.dumps({"model": PROMPT["modelo"], "instrucciones": PROMPT["instrucciones"],
                       "entrada": bloque_de_datos(descripcion_icp, nombre, ciudad, actividad)},
                      ensure_ascii=False).encode("utf-8")


def tokens_validos(tokens_in: object) -> int | None:
    """None si jev no informó un uso legible; el que llama cobra el techo y lanza UsoJevInvalido."""
    if type(tokens_in) is not int or tokens_in < 0:  # type(): para isinstance, bool es int
        return None
    return tokens_in


def operacion_jev(lead_id: UUID, tokens_in: int, usd_in_por_M: Decimal) -> OperacionCosto:
    return OperacionCosto(tipo="jev_tokens", unidades=Decimal(tokens_in), costo_unitario=usd_in_por_M / Decimal(1_000_000),
                          moneda="USD", proveedor="jev", fuente=None, canal=None, lead_id=lead_id, lote_id=None,
                          gratis=False)


def validar_salida(salida: object) -> Encaje:
    if not isinstance(salida, dict) or salida.get("etiqueta") not in ETIQUETAS:
        raise SalidaJevInvalida
    p = salida.get("probabilidad")
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1:  # NaN falla la doble desigualdad
        raise SalidaJevInvalida
    return Encaje(salida["etiqueta"], float(p))


class JevClasificador:
    def __init__(self, registro_costos: RegistroCostos, transporte: httpx.BaseTransport, url: str,
                 credencial: SecretStr, usd_in_por_M: Decimal):
        self._costos = registro_costos
        self._transporte = transporte
        self._url = url
        self._credencial = credencial  # SecretStr: no sale en repr
        self._usd_in_por_M = usd_in_por_M

    def clasificar(self, lead_id: UUID, descripcion_icp: str, nombre: str, ciudad: str | None,
                   actividad: str | None) -> Encaje:
        # ponytail: formato de cable provisional (P8/D10 sin documentar); se ajusta acá cuando haya acceso a jev.
        with httpx.Client(transport=self._transporte, trust_env=False, timeout=TIMEOUT_S) as cliente:
            contenido = cuerpo_jev(descripcion_icp, nombre, ciudad, actividad)
            try:
                respuesta = cliente.post(self._url, headers={"Authorization": f"Bearer {self._credencial.get_secret_value()}",
                                                             "Content-Type": "application/json"}, content=contenido)
            except httpx.TimeoutException:
                respuesta = None  # timeout propio: no sabemos si jev procesó
        if respuesta is None or respuesta.status_code >= 500:
            # 500/502/503: jev no procesó, fila en 0. 504 y timeout: pudo haber procesado, techo. Siempre hay fila.
            no_proceso = respuesta is not None and respuesta.status_code in NO_PROCESO
            self._costos.registrar(operacion_jev(lead_id, 0 if no_proceso else len(contenido), self._usd_in_por_M))
            raise JevNoDisponible  # sin cuerpo ni datos del lead: solo la clase
        if respuesta.is_error:  # 4xx: jev rechazó sin procesar; credencial o pedido mal armados, corta la corrida
            self._costos.registrar(operacion_jev(lead_id, 0, self._usd_in_por_M))
            respuesta.raise_for_status()
        try:
            cuerpo = respuesta.json()
        except ValueError:
            cuerpo = SIN_JSON
        uso = cuerpo.get("uso") if isinstance(cuerpo, dict) else None
        tokens_in = tokens_validos(uso.get("tokens_in") if isinstance(uso, dict) else None)
        # Salió y se pagó: sin uso legible se cobra el techo, como JuezClaude (un token >= un byte del body).
        self._costos.registrar(operacion_jev(lead_id, len(contenido) if tokens_in is None else tokens_in,
                                             self._usd_in_por_M))
        if cuerpo is SIN_JSON:  # fuera del except: el error no cuelga la decodificación ni el cuerpo
            raise SalidaJevInvalida
        if tokens_in is None:
            raise UsoJevInvalido
        return validar_salida(cuerpo.get("salida"))
