"""Puerta B: una frase libre (o una conversación corta) -> `Sugerencia`, o una pregunta si falta saber a quién le vende.
Un reintento si la salida no matchea el esquema. Enmienda 2026-10-18: conversación de hasta MAX_TURNOS turnos.

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
MAX_TURNOS = 12  # historial previo: 6 idas y vueltas; con 6 turnos el QA cortaba la charla demasiado pronto
MAX_TEXTO_IA = 240  # pregunta y explicación del modelo: una línea, se muestran tal cual (React escapa)
INTENTOS = 2  # el primero y un reintento
ROLES = {"usuario": "Usuario", "asistente": "Asistente"}


@dataclass(frozen=True)
class ResultadoFrase:
    sugerencia: Sugerencia
    costo_usd: Decimal
    lote_id: UUID
    pregunta: str | None = None  # la IA no tiene claro a quién le vende: lo pregunta en vez de adivinar
    explicacion: str | None = None  # por qué propone esos filtros, en una línea
    ciiu_descartado: bool = False  # el modelo propuso un CIIU fuera del catálogo y la validación lo dejó en null


def _texto_ia(valor) -> str | None:
    if not isinstance(valor, str):
        return None
    limpio = " ".join(valor.split())[:MAX_TEXTO_IA]
    return limpio or None


class InterpretarFrase:
    def __init__(self, generador: GeneradorEstructurado, costos: RegistroCostos, geografia: Mapping[str, dict],
                 actividades: Mapping, nuevo_lote: Callable[[], UUID] = uuid4):
        self._generador, self._costos = generador, costos
        self._geografia, self._actividades, self._nuevo_lote = geografia, actividades, nuevo_lote

    def ejecutar(self, frase: str, historial=()) -> ResultadoFrase:
        frase = frase.strip()
        historial = list(historial)
        if not frase or len(frase) > MAX_FRASE or len(historial) > MAX_TURNOS:
            raise FraseFueraDeRango("largo")
        if any(rol not in ROLES or not isinstance(t, str) or len(t) > MAX_FRASE for rol, t in historial):
            raise FraseFueraDeRango("historial")
        if historial:  # una sola entrada para el modelo: la conversación entera, que el adaptador delimita como dato
            frase = "\n".join([f"{ROLES[rol]}: {t.strip()}" for rol, t in historial] + [f"Usuario: {frase}"])
        lote_id = self._nuevo_lote()  # sin fila propia: costos.lote_id no tiene FK
        for intento in range(INTENTOS):
            try:
                crudo = self._generador.generar(frase, lote_id)
                sugerencia = validar_sugerencia(crudo, self._geografia, self._actividades)
            except SalidaIntakeInvalida:
                if intento == INTENTOS - 1:
                    raise
                continue  # mismo prompt, misma frase: los tokens del primero ya quedaron cobrados
            return ResultadoFrase(sugerencia, self._costos.gasto_busqueda(lote_id), lote_id,
                                  pregunta=_texto_ia(crudo.get("pregunta")), explicacion=_texto_ia(crudo.get("explicacion")),
                                  ciiu_descartado=bool(str(crudo.get("ciiu") or "").strip()) and sugerencia.ciiu is None)
        raise AssertionError("inalcanzable")  # pragma: no cover
