"""JuezClaude: stub de T013. La implementación real (Messages API con tool_use) es T018."""
from uuid import UUID

import httpx

from app.modulos.costos.dominio.puertos import RegistroCostos
from evals.jueces.puerto import Veredicto


class JuezClaude:
    determinista_si_se_demuestra = False

    def __init__(self, registro_costos: RegistroCostos, tarifa: dict, modelo: str, prompt: str,
                 lote_id: UUID, http_client: httpx.Client):
        self._costos = registro_costos
        self._tarifa, self._modelo, self._prompt = tarifa, modelo, prompt
        self._lote_id, self._http = lote_id, http_client

    def juzgar(self, tarea: str, caso: dict) -> Veredicto:
        return Veredicto(-1.0, "")  # stub: sin request ni costos; fuera de rango a propósito
