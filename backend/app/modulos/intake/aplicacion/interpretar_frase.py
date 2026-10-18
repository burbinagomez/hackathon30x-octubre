"""Puerta B: una frase libre -> `Sugerencia`. Un turno, sin chat. Un reintento si la salida no matchea el esquema.

El caso de uso no escribe costos ni los inventa: el adaptador los registra por llamada con el `lote_id` de la corrida
(principio VIII); acá solo se lee el total del lote para devolverlo. Nada de la frase ni de la respuesta se loguea.
"""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.intake.dominio.errores import FraseFueraDeRango, SalidaIntakeInvalida
from app.modulos.intake.dominio.puertos import GeneradorEstructurado
from app.modulos.intake.dominio.sugerencia import Sugerencia, validar_sugerencia

MAX_FRASE = 500
INTENTOS = 2  # el primero y un reintento


@dataclass(frozen=True)
class ResultadoFrase:
    sugerencia: Sugerencia
    costo_usd: Decimal
    lote_id: UUID


class InterpretarFrase:
    def __init__(self, generador: GeneradorEstructurado, costos: RegistroCostos, geografia: Mapping[str, dict],
                 actividades: Mapping, nuevo_lote: Callable[[], UUID] = uuid4):
        self._generador, self._costos = generador, costos
        self._geografia, self._actividades, self._nuevo_lote = geografia, actividades, nuevo_lote

    def ejecutar(self, frase: str) -> ResultadoFrase:
        frase = frase.strip()
        if not frase or len(frase) > MAX_FRASE:
            raise FraseFueraDeRango("largo")
        lote_id = self._nuevo_lote()  # sin fila propia: costos.lote_id no tiene FK
        for intento in range(INTENTOS):
            try:
                sugerencia = validar_sugerencia(self._generador.generar(frase, lote_id), self._geografia, self._actividades)
            except SalidaIntakeInvalida:
                if intento == INTENTOS - 1:
                    raise
                continue  # mismo prompt, misma frase: los tokens del primero ya quedaron cobrados
            return ResultadoFrase(sugerencia, self._costos.gasto_busqueda(lote_id), lote_id)
        raise AssertionError("inalcanzable")  # pragma: no cover
