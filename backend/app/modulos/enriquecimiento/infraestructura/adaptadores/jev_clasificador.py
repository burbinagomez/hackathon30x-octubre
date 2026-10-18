"""jev_clasificador: pregunta a jev si el lead encaja con el ICP.

Defensas: los datos del lead van como JSON dentro de un bloque delimitado, con < y > escapados (un nombre no
abre ni cierra el bloque); las instrucciones salen de encaje_jev_v1.json, nunca del lead. El costo se registra
con los tokens que informa jev, antes de validar la salida: una salida rota también se paga.
"""
import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
from pydantic import SecretStr

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.enriquecimiento.dominio.errores import SalidaJevInvalida, UsoJevInvalido
from app.modulos.enriquecimiento.dominio.puertos import Encaje

PROMPT = json.loads((Path(__file__).parent / "encaje_jev_v1.json").read_text(encoding="utf-8"))
TIMEOUT_S = 30.0
ETIQUETAS = {"encaja", "no_encaja", "ninguna"}


def bloque_de_datos(descripcion_icp: str, nombre: str, ciudad: str | None, actividad: str | None) -> str:
    datos = json.dumps({"actividad_declarada": actividad, "nombre_negocio": nombre, "ciudad": ciudad,
                        "descripcion_icp": descripcion_icp}, ensure_ascii=False)
    datos = datos.replace("<", "\\u003c").replace(">", "\\u003e")  # escape JSON válido: json.loads devuelve el texto
    return f"<datos_del_lead>\n{datos}\n</datos_del_lead>"


def validar_tokens(tokens_in: object) -> int:
    if type(tokens_in) is not int or tokens_in < 0:  # type(): para isinstance, bool es int
        raise UsoJevInvalido
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
            respuesta = cliente.post(self._url, headers={"Authorization": f"Bearer {self._credencial.get_secret_value()}"},
                                     json={"model": PROMPT["modelo"], "instrucciones": PROMPT["instrucciones"],
                                           "entrada": bloque_de_datos(descripcion_icp, nombre, ciudad, actividad)})
            respuesta.raise_for_status()  # 5xx o timeout: jev no midió tokens, no hay fila
        cuerpo = respuesta.json()
        uso = cuerpo.get("uso") if isinstance(cuerpo, dict) else None
        tokens_in = validar_tokens(uso.get("tokens_in") if isinstance(uso, dict) else None)
        self._costos.registrar(operacion_jev(lead_id, tokens_in, self._usd_in_por_M))
        return validar_salida(cuerpo.get("salida"))
