"""Suite de contrato del puerto `Calificador`: todo adaptador la pasa (advisor). Parametrizada sobre `DaptaCSV`
(formato CSV real) y `CalificadorFalso` (formato JSON de prueba): mismos datos semánticos, mismo resultado."""
import csv
import io
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modulos.calificacion.dominio.errores import ArchivoInvalido
from app.modulos.calificacion.dominio.modelos import FilaRechazada, ResultadoCalificacion
from app.modulos.calificacion.infraestructura.dapta_csv import DaptaCSV
from tests.falsos import CalificadorFalso

LEAD = uuid4()
FECHA = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _csv(filas: list[dict]) -> bytes:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=["lead_id", "calificado", "fecha", "minutos", "extra"])
    w.writeheader()
    for f in filas:
        w.writerow({"lead_id": "", "calificado": "", "fecha": "", "minutos": "", "extra": "ruido", **f})
    return out.getvalue().encode("utf-8-sig")  # con BOM: el adaptador lo acepta (plan.md)


def _json(filas: list[dict]) -> bytes:
    return json.dumps([{"extra": "ruido", **f} for f in filas]).encode("utf-8")


ADAPTADORES = {"dapta_csv": (DaptaCSV, _csv), "falso": (CalificadorFalso, _json)}


@pytest.mark.parametrize("nombre", sorted(ADAPTADORES))
def test_leer_resultados_mapea_si_no_fecha_minutos(nombre):
    clase, construir = ADAPTADORES[nombre]
    archivo = construir([{"lead_id": str(LEAD), "calificado": "si", "fecha": FECHA.isoformat(), "minutos": "3.5"}])

    resultados = clase().leer_resultados(archivo)

    assert resultados == [ResultadoCalificacion(LEAD, True, FECHA, Decimal("3.5"))]


@pytest.mark.parametrize("nombre", sorted(ADAPTADORES))
def test_valor_desconocido_es_fila_rechazada_no_excepcion(nombre):
    clase, construir = ADAPTADORES[nombre]
    archivo = construir([{"lead_id": str(LEAD), "calificado": "tal_vez", "fecha": FECHA.isoformat(), "minutos": "1"}])

    resultados = clase().leer_resultados(archivo)

    assert resultados == [FilaRechazada(1, "valor_invalido")]


@pytest.mark.parametrize("nombre", sorted(ADAPTADORES))
def test_columnas_no_mapeadas_se_ignoran(nombre):
    clase, construir = ADAPTADORES[nombre]
    archivo = construir([{"lead_id": str(LEAD), "calificado": "no", "fecha": FECHA.isoformat(), "minutos": "0",
                           "extra": "+573001112233"}])

    resultados = clase().leer_resultados(archivo)

    assert resultados == [ResultadoCalificacion(LEAD, False, FECHA, Decimal("0"))]


@pytest.mark.parametrize("nombre", sorted(ADAPTADORES))
def test_archivo_sobre_limite_es_entrada_invalida(nombre):
    clase, construir = ADAPTADORES[nombre]
    archivo = construir([{"lead_id": str(uuid4()), "calificado": "si", "fecha": FECHA.isoformat(), "minutos": "1"}
                          for _ in range(1001)])

    with pytest.raises(ArchivoInvalido):
        clase().leer_resultados(archivo)


def test_rechazo_no_expone_el_valor_crudo():
    # Mutación `rechazo_lleva_valor`: si FilaRechazada guardara el valor de la columna, el teléfono aparecería
    # en el repr de la salida. Sale en `calificado` (valor inválido), que es la columna que se rechaza.
    archivo = _csv([{"lead_id": str(LEAD), "calificado": "+573001112233", "fecha": FECHA.isoformat(), "minutos": "1"}])

    resultados = DaptaCSV().leer_resultados(archivo)

    assert "+573001112233" not in repr(resultados)


@pytest.mark.parametrize("nombre", sorted(ADAPTADORES))
@pytest.mark.parametrize("minutos", ["NaN", "sNaN"])
def test_minutos_nan_es_fila_rechazada_no_excepcion(nombre, minutos):
    # security (LOW): Decimal("NaN") se construye bien pero compararlo con 0..60 lanza InvalidOperation -> 500.
    clase, construir = ADAPTADORES[nombre]
    archivo = construir([{"lead_id": str(LEAD), "calificado": "si", "fecha": FECHA.isoformat(), "minutos": minutos}])

    assert clase().leer_resultados(archivo) == [FilaRechazada(1, "valor_invalido")]


def test_campo_enorme_es_archivo_invalido_no_excepcion():
    # security (LOW): un campo de más de csv.field_size_limit() (131072) lanza csv.Error -> 500.
    archivo = _csv([{"lead_id": str(LEAD), "calificado": "si", "fecha": FECHA.isoformat(), "minutos": "1",
                     "extra": "x" * 200_000}])

    with pytest.raises(ArchivoInvalido):
        DaptaCSV().leer_resultados(archivo)
