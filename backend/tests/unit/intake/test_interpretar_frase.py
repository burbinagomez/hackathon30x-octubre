"""InterpretarFrase: un turno, un reintento si la salida no matchea, costos antes de devolver (fuente='intake')."""
import logging
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modulos.intake.aplicacion.interpretar_frase import MAX_FRASE, MAX_TURNOS, InterpretarFrase
from app.modulos.intake.dominio.errores import ErrorGeneracion, FraseFueraDeRango, SalidaIntakeInvalida
from app.modulos.intake.dominio.sugerencia import Sugerencia
from app.modulos.intake.infraestructura.llm.interpretador_claude import InterpretadorClaude
from tests.anthropic_intake_falso import CLAVE_FALSA, MODELO, SIN_PAIS, VALIDA, cliente, respuesta
from tests.falsos import RegistroCostosFalso
from tests.unit.intake.test_sugerencia import ACTIVIDADES, GEOGRAFIA

FRASE = "vendo software contable a ferreterías medianas en Antioquia"
TARIFA = {"in_usd_por_M": Decimal("0.10"), "out_usd_por_M": Decimal("0.50")}


class GeneradorFalso:
    """Devuelve (o lanza) lo que se le dio, en orden; la última se repite. Anota cada llamada."""

    def __init__(self, *salidas):
        self.salidas, self.llamadas = list(salidas), []

    def generar(self, frase, lote_id):
        self.llamadas.append((frase, lote_id))
        s = self.salidas.pop(0) if len(self.salidas) > 1 else self.salidas[0]
        if isinstance(s, Exception):
            raise s
        return s


def caso(generador, costos=None):
    return InterpretarFrase(generador, costos or RegistroCostosFalso(), GEOGRAFIA, ACTIVIDADES)


def test_salida_valida_mapea_a_la_sugerencia_con_codigos():
    r = caso(GeneradorFalso(VALIDA)).ejecutar(FRASE)

    assert r.sugerencia == Sugerencia(pais="CO", ciiu="4752", departamento="05", ciudad=None, ingresos_min=500000000,
                                      palabras_clave=("ferretería",), exclusiones=())


def test_ciiu_alucinado_sale_null_sin_error_ni_reintento():
    g = GeneradorFalso({**VALIDA, "ciiu": "9999"})

    r = caso(g).ejecutar(FRASE)

    assert r.sugerencia.ciiu is None and len(g.llamadas) == 1


def test_reintenta_una_vez_con_la_misma_frase_si_la_salida_no_matchea():
    g = GeneradorFalso(SIN_PAIS, VALIDA)

    r = caso(g).ejecutar(FRASE)

    assert r.sugerencia.pais == "CO"
    assert [f for f, _ in g.llamadas] == [FRASE, FRASE]


def test_dos_salidas_invalidas_son_salida_intake_invalida_y_no_hay_tercer_intento():
    g = GeneradorFalso(SIN_PAIS, SalidaIntakeInvalida("sin_tool_use"))

    with pytest.raises(SalidaIntakeInvalida):
        caso(g).ejecutar(FRASE)

    assert len(g.llamadas) == 2


def test_error_del_proveedor_no_se_reintenta():
    g = GeneradorFalso(ErrorGeneracion("http_500"))

    with pytest.raises(ErrorGeneracion):
        caso(g).ejecutar(FRASE)

    assert len(g.llamadas) == 1


@pytest.mark.parametrize("frase", ["", "   ", "x" * (MAX_FRASE + 1)], ids=["vacia", "espacios", "501"])
def test_frase_vacia_o_de_mas_de_500_caracteres_no_llega_al_modelo(frase):
    g = GeneradorFalso(VALIDA)

    with pytest.raises(FraseFueraDeRango):
        caso(g).ejecutar(frase)

    assert g.llamadas == []


def test_frase_de_exactamente_500_caracteres_pasa():
    assert caso(GeneradorFalso(VALIDA)).ejecutar("x" * MAX_FRASE).sugerencia.pais == "CO"


def test_los_dos_intentos_comparten_el_lote_y_cada_corrida_trae_el_suyo():
    g = GeneradorFalso(SIN_PAIS, VALIDA)
    uso = caso(g)

    primera = uso.ejecutar(FRASE)
    segunda = uso.ejecutar(FRASE)

    assert g.llamadas[0][1] == g.llamadas[1][1] == primera.lote_id
    assert segunda.lote_id != primera.lote_id


# --- con el adaptador real y transporte falso: lo que queda en el libro de costos --------------------------------

def con_adaptador(*respuestas):
    costos = RegistroCostosFalso()
    adaptador = InterpretadorClaude(costos, TARIFA, MODELO, CLAVE_FALSA, cliente([], *respuestas))
    return caso(adaptador, costos), costos


def test_registra_llm_tokens_con_fuente_intake_antes_de_retornar():
    uso, costos = con_adaptador(respuesta(VALIDA))

    r = uso.ejecutar(FRASE)

    assert [(o.tipo, o.fuente, o.lead_id, o.lote_id) for o in costos.filas] == [
        ("llm_tokens_in", "intake", None, r.lote_id), ("llm_tokens_out", "intake", None, r.lote_id)]
    assert r.costo_usd == Decimal(200) * Decimal("0.10") / 1_000_000 + Decimal(60) * Decimal("0.50") / 1_000_000


def test_salida_invalida_igual_registra_costos_de_las_dos_llamadas():
    uso, costos = con_adaptador(respuesta(SIN_PAIS), respuesta(SIN_PAIS))

    with pytest.raises(SalidaIntakeInvalida):
        uso.ejecutar(FRASE)

    assert [o.tipo for o in costos.filas] == ["llm_tokens_in", "llm_tokens_out"] * 2
    assert len({o.lote_id for o in costos.filas}) == 1


def test_la_primera_llamada_deja_sus_filas_antes_del_reintento():
    costos, vistas = RegistroCostosFalso(), []
    adaptador = InterpretadorClaude(costos, TARIFA, MODELO, CLAVE_FALSA, cliente([], respuesta(SIN_PAIS), respuesta(VALIDA)))

    class Espia:
        def generar(self, frase, lote_id):
            vistas.append(len(costos.filas))  # filas que ya había al empezar cada llamada
            return adaptador.generar(frase, lote_id)

    caso(Espia(), costos).ejecutar(FRASE)

    assert vistas == [0, 2]


def test_la_frase_y_la_respuesta_nunca_salen_en_logs(caplog):
    caplog.set_level(logging.DEBUG)
    frase = "ferreterías ZZ-FRASE-SECRETA-123"
    uso, _ = con_adaptador(respuesta({**SIN_PAIS, "palabras_clave": ["ZZ-RESPUESTA-456"]}),
                           respuesta({**SIN_PAIS, "palabras_clave": ["ZZ-RESPUESTA-456"]}))

    with pytest.raises(SalidaIntakeInvalida) as e:
        uso.ejecutar(frase)

    assert "ZZ-" not in caplog.text and "ZZ-" not in str(e.value) and "ZZ-" not in repr(e.value)


# --- Conversación (enmienda 2026-10-18): la IA pregunta si falta a quién le vende, y explica lo que propone ---------

def test_si_la_ia_pregunta_la_pregunta_viaja_y_no_hace_falta_sugerencia_completa():
    r = caso(GeneradorFalso({**VALIDA, "pregunta": "¿A qué tipo de empresas le vendés?", "explicacion": None})).ejecutar(
        "desarrollo de software a la medida")
    assert r.pregunta == "¿A qué tipo de empresas le vendés?"


def test_la_explicacion_viaja_recortada_y_sin_saltos():
    larga = "Busco ferreterías\nen Antioquia " + "x" * 500
    r = caso(GeneradorFalso({**VALIDA, "pregunta": None, "explicacion": larga})).ejecutar(FRASE)
    assert r.pregunta is None
    assert len(r.explicacion) <= 240 and "\n" not in r.explicacion


def test_el_historial_viaja_como_conversacion_delimitada_en_un_solo_dato():
    g = GeneradorFalso({**VALIDA, "pregunta": None, "explicacion": "ok"})
    caso(g).ejecutar("a ferreterías de Antioquia", historial=[("usuario", "vendo software a la medida"),
                                                             ("asistente", "¿A qué tipo de empresas le vendés?")])
    texto = g.llamadas[0][0]
    assert texto.index("Usuario: vendo software") < texto.index("Asistente: ¿A qué") < texto.index("Usuario: a ferreterías")


def test_el_historial_tiene_tope():
    with pytest.raises(FraseFueraDeRango):
        caso(GeneradorFalso(VALIDA)).ejecutar("x", historial=[("usuario", "y")] * (MAX_TURNOS + 1))


def test_el_tope_de_turnos_es_12_y_12_pasan():
    assert MAX_TURNOS == 12
    assert caso(GeneradorFalso(VALIDA)).ejecutar("x", historial=[("usuario", "y")] * 12).sugerencia.pais == "CO"


def test_ciiu_fuera_del_catalogo_marca_ciiu_descartado():
    r = caso(GeneradorFalso({**VALIDA, "ciiu": "8521"})).ejecutar(FRASE)

    assert r.sugerencia.ciiu is None and r.ciiu_descartado is True


@pytest.mark.parametrize("ciiu,descartado", [("4752", False), (None, False), ("", False)], ids=["valido", "null", "vacio"])
def test_ciiu_valido_o_ausente_no_marca_descartado(ciiu, descartado):
    r = caso(GeneradorFalso({**VALIDA, "ciiu": ciiu})).ejecutar(FRASE)

    assert r.ciiu_descartado is descartado
