"""JuezClaude: stub de T013. La implementación real (Messages API con tool_use) es T018."""
from uuid import UUID

import httpx

from app.modulos.costos.dominio.puertos import RegistroCostos
from evals.jueces.puerto import Veredicto


class JuezClaude:
    determinista_si_se_demuestra = False

    def __init__(self, registro_costos: RegistroCostos, tarifa: dict, modelo: str, prompt: str,
                 lote_id: UUID, api_key: str, http_client: httpx.Client):
        # La key llega por constructor (la lee la composición de T019 desde `entorno`); nunca del entorno acá.
        self._costos = registro_costos
        self._tarifa, self._modelo, self._prompt = tarifa, modelo, prompt
        self._lote_id, self._api_key, self._http = lote_id, api_key, http_client

    def juzgar(self, tarea: str, caso: dict) -> Veredicto:
        return Veredicto(-1.0, "")  # stub: sin request ni costos; fuera de rango a propósito
