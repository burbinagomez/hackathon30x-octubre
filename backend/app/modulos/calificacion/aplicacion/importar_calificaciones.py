from decimal import Decimal

from app.modulos.calificacion.dominio.errores import TarifaPendiente
from app.modulos.calificacion.dominio.modelos import FilaRechazada, ResultadoCalificacion, ResumenImportacion
from app.modulos.calificacion.dominio.puertos import Calificador, RepositorioCalificaciones
from app.modulos.calificacion.dominio.tarifas import minutos_facturables
from app.modulos.costos.dominio.modelos import OperacionCosto


class ImportarCalificaciones:
    """Guarda cada resultado del CSV de Dapta y escribe `dapta_llamada` en `costos` para el que entra como
    `importada`. El repo (infraestructura) hace calificación + costo en una sola transacción (T011): acá solo
    se calcula la `OperacionCosto` y se respeta lo que el repo decide para cada fila."""

    def __init__(self, calificador: Calificador, repo: RepositorioCalificaciones, tarifa_usd_por_minuto: Decimal | None):
        self._calificador = calificador
        self._repo = repo
        self._tarifa = tarifa_usd_por_minuto

    def ejecutar(self, archivo: bytes) -> ResumenImportacion:
        if self._tarifa is None:
            raise TarifaPendiente()  # antes de tocar una fila (plan.md)

        contadores = {"importada": 0, "duplicada": 0, "conflicto": 0, "no_cumple": 0, "ref_desconocida": 0}
        rechazadas: list[FilaRechazada] = []
        for item in self._calificador.leer_resultados(archivo):
            if isinstance(item, FilaRechazada):
                rechazadas.append(item)
                continue
            costo = self._costo(item)
            estado = self._repo.guardar(item, costo)
            contadores[estado] += 1

        return ResumenImportacion(
            importadas=contadores["importada"], duplicadas=contadores["duplicada"],
            conflictos=contadores["conflicto"], no_cumple=contadores["no_cumple"],
            ref_desconocida=contadores["ref_desconocida"], rechazadas=tuple(rechazadas),
        )

    def _costo(self, resultado: ResultadoCalificacion) -> OperacionCosto:
        return OperacionCosto(
            tipo="dapta_llamada", unidades=minutos_facturables(resultado.minutos), costo_unitario=self._tarifa,
            moneda="USD", proveedor="dapta", fuente=None, canal=None, lead_id=resultado.lead_id, lote_id=None,
            gratis=False, ts=resultado.fecha,
        )
