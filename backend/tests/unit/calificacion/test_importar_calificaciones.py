"""Unitarios de `ImportarCalificaciones` (advisor): repo falso y `RegistroCostosFalso` en memoria.

El repo encapsula la atomicidad calificación+costo (T010/T011, integración real): acá solo se prueba que el
caso de uso calcula bien la `OperacionCosto` (minutos redondeados, tarifa, `ts`) y respeta lo que el repo decide."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modulos.calificacion.dominio.errores import TarifaPendiente
from app.modulos.calificacion.dominio.modelos import FilaRechazada, ResultadoCalificacion
from app.modulos.calificacion.aplicacion.importar_calificaciones import ImportarCalificaciones
from tests.falsos import RegistroCostosFalso, RepositorioCalificacionesFalso

LEAD = uuid4()
FECHA = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
TARIFA = Decimal("0.333")


class CalificadorFalsoDeResultados:
    """Doble mínimo del puerto `Calificador`: devuelve exactamente lo que le dan, sin leer bytes."""

    def __init__(self, items):
        self._items = items

    def leer_resultados(self, archivo):
        return self._items


def _caso(items, tarifa=TARIFA, estados=None):
    costos = RegistroCostosFalso()
    repo = RepositorioCalificacionesFalso(costos, estados)
    caso = ImportarCalificaciones(CalificadorFalsoDeResultados(items), repo, tarifa)
    return caso, repo, costos


def test_calificado_escribe_dapta_llamada_con_minutos_y_tarifa():
    resultado = ResultadoCalificacion(LEAD, True, FECHA, Decimal("2.1"))
    caso, repo, costos = _caso([resultado])

    resumen = caso.ejecutar(b"")

    assert resumen.importadas == 1
    fila = costos.filas[0]
    assert fila.tipo == "dapta_llamada"
    assert fila.unidades == Decimal("3")  # ceil(2.1)
    assert fila.costo_unitario == TARIFA
    assert type(fila.unidades) is Decimal and type(fila.costo_unitario) is Decimal
    assert fila.proveedor == "dapta"
    assert fila.fuente is None and fila.canal is None
    assert fila.lead_id == LEAD


def test_tarifa_null_es_tarifa_pendiente_y_no_escribe_nada():
    resultado = ResultadoCalificacion(LEAD, True, FECHA, Decimal("2"))
    caso, repo, costos = _caso([resultado], tarifa=None)

    with pytest.raises(TarifaPendiente):
        caso.ejecutar(b"")

    assert costos.filas == []
    assert repo.guardadas == []


def test_duplicada_no_escribe_costo_de_nuevo():
    resultado = ResultadoCalificacion(LEAD, True, FECHA, Decimal("2"))
    caso, repo, costos = _caso([resultado], estados={LEAD: "duplicada"})

    resumen = caso.ejecutar(b"")

    assert resumen.duplicadas == 1
    assert resumen.importadas == 0
    assert costos.filas == []


def test_conflicto_no_cambia_nada():
    resultado = ResultadoCalificacion(LEAD, False, FECHA, Decimal("2"))
    caso, repo, costos = _caso([resultado], estados={LEAD: "conflicto"})

    resumen = caso.ejecutar(b"")

    assert resumen.conflictos == 1
    assert costos.filas == []
    assert repo.guardadas == []


def test_ts_del_costo_es_la_fecha_de_la_llamada():
    resultado = ResultadoCalificacion(LEAD, True, FECHA, Decimal("1"))
    caso, repo, costos = _caso([resultado])

    caso.ejecutar(b"")

    assert costos.filas[0].ts == FECHA


def test_filas_rechazadas_no_llegan_al_repo():
    caso, repo, costos = _caso([FilaRechazada(1, "valor_invalido")])

    resumen = caso.ejecutar(b"")

    assert resumen.rechazadas == (FilaRechazada(1, "valor_invalido"),)
    assert repo.guardadas == []
    assert costos.filas == []
