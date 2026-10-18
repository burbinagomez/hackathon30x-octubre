"""Falsos en memoria de los puertos. Mismo contrato que Postgres: dedup por (pais, id_fiscal), ON CONFLICT en lead_fuentes."""
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.modulos.calificacion.dominio.mapeo import mapear_fila
from app.modulos.calificacion.dominio.errores import ArchivoInvalido
from app.modulos.calificacion.dominio.modelos import FilaRechazada, ResultadoCalificacion
from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.descubrimiento.dominio.errores import ErrorPersistencia
from app.modulos.descubrimiento.dominio.modelos import Borrador, CriteriosICP, EmpresaCruda, MetaFuente, PaginaEmpresas


class RepositorioLeadsFalso:
    def __init__(self, falla_si=None):
        self._falla_si = falla_si  # empresa -> bool: si es True, guardarla lanza ErrorPersistencia (la base la rechazó)
        self.busquedas: dict[UUID, str] = {}  # id -> estado
        self.leads: dict[tuple[str, str | None], UUID] = {}  # (pais, id_fiscal) -> id
        self.cumplimiento: dict[UUID, tuple] = {}  # lead_id -> (fuente, licencia, url_origen, as_of)
        self.lead_fuentes: set[tuple[UUID, str, UUID]] = set()  # (lead_id, fuente, busqueda_id)
        self.licencia_lead_fuente: dict[tuple[UUID, str, UUID], str] = {}  # la licencia con que se anotó cada fila
        self.borradores: dict[UUID, tuple] = {}  # id -> (criterios, canal_preferido, tope_gasto_usd, mensaje_base)

    def crear_busqueda(self, criterios: CriteriosICP) -> UUID:
        busqueda_id = uuid4()
        self.busquedas[busqueda_id] = "creada"
        return busqueda_id

    def crear_borrador(self, criterios: CriteriosICP, canal_preferido: str | None, tope_gasto_usd: Decimal,
                       mensaje_base: str | None) -> UUID:
        """P2: mismo contrato que Postgres. Estado `borrador`, criterios congelados."""
        busqueda_id = uuid4()
        self.busquedas[busqueda_id] = "borrador"
        self.borradores[busqueda_id] = (criterios, canal_preferido, tope_gasto_usd, mensaje_base)
        return busqueda_id

    def estado(self, busqueda_id: UUID) -> str | None:
        return self.busquedas.get(busqueda_id)

    def obtener_borrador(self, busqueda_id: UUID) -> Borrador | None:
        if self.busquedas.get(busqueda_id) != "borrador":
            return None
        criterios, canal, tope, mensaje = self.borradores[busqueda_id]
        return Borrador(busqueda_id, criterios, canal, tope, mensaje)

    def pasar_a_ejecutando(self, busqueda_id: UUID) -> bool:
        if self.busquedas.get(busqueda_id) != "borrador":
            return False
        self.busquedas[busqueda_id] = "ejecutando"
        return True

    @contextmanager
    def transaccion(self) -> Iterator[None]:
        yield

    @contextmanager
    def savepoint(self) -> Iterator[None]:
        """Como el de Postgres: si lo de adentro lanza, se deshace todo lo que se escribió ahí y la excepción sigue."""
        antes = (dict(self.leads), dict(self.cumplimiento), set(self.lead_fuentes), dict(self.licencia_lead_fuente))
        try:
            yield
        except BaseException:
            self.leads, self.cumplimiento, self.lead_fuentes, self.licencia_lead_fuente = antes
            raise

    def obtener_o_crear_lead(self, e: EmpresaCruda, licencia: str) -> tuple[UUID, bool]:
        if self._falla_si is not None and self._falla_si(e):
            raise ErrorPersistencia("la base rechazó la operación")
        clave = (e.pais, e.id_fiscal)
        if e.id_fiscal is not None and clave in self.leads:
            return self.leads[clave], False
        lead_id = uuid4()
        self.leads[clave if e.id_fiscal is not None else (e.pais, str(lead_id))] = lead_id
        self.cumplimiento[lead_id] = (e.fuente, licencia, e.url_origen, e.as_of)
        return lead_id, True

    def agregar_lead_fuente(self, lead_id: UUID, busqueda_id: UUID, e: EmpresaCruda, licencia: str) -> None:
        self.lead_fuentes.add((lead_id, e.fuente, busqueda_id))
        self.licencia_lead_fuente[(lead_id, e.fuente, busqueda_id)] = licencia

    def cerrar_busqueda(self, busqueda_id: UUID, estado: str) -> None:
        self.busquedas[busqueda_id] = estado


class RegistroCostosFalso:
    def __init__(self, requests_24h: int = 0, creditos_mes: Decimal = Decimal(0), proveedor: str = "croma"):
        """Los contadores son POR PROVEEDOR, como en Postgres: el límite de Croma es de la cuenta, compartido por todos sus
        endpoints. Un adaptador que consulte otra clave (p. ej. su `meta.clave`) ve 0 y no frena nunca."""
        self.filas: list[OperacionCosto] = []
        self._requests_24h = {proveedor: requests_24h}
        self._creditos_mes = {proveedor: creditos_mes}

    def registrar(self, op: OperacionCosto) -> None:
        self.filas.append(op)

    def requests_24h(self, proveedor: str) -> int:
        return self._requests_24h.get(proveedor, 0)

    def creditos_mes(self, proveedor: str) -> Decimal:
        return self._creditos_mes.get(proveedor, Decimal(0))

    def gasto_busqueda(self, busqueda_id: UUID) -> Decimal:
        return sum((op.unidades * op.costo_unitario for op in self.filas if op.lote_id == busqueda_id), Decimal(0))


class FuenteFalsa:
    """Escribe 1 fila de costos con su lote_id y devuelve sus empresas del país pedido en la página 1, o lanza `error`."""

    def __init__(self, meta: MetaFuente, costos: RegistroCostosFalso, lote_id: UUID,
                 empresas: tuple[EmpresaCruda, ...] = (), error: Exception | None = None,
                 recibidos: dict[str, CriteriosICP] | None = None, costo_unitario: Decimal = Decimal(0)):
        self.meta = meta
        self._costo_unitario = costo_unitario
        self._recibidos = recibidos
        self._costos = costos
        self._lote_id = lote_id
        self._empresas = empresas
        self._error = error

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        if self._recibidos is not None:
            self._recibidos[self.meta.clave] = criterios
        self._costos.registrar(OperacionCosto(
            tipo="web_fetch", unidades=Decimal(1), costo_unitario=self._costo_unitario, moneda="USD",
            proveedor=self.meta.proveedor, fuente=self.meta.clave, canal=None, lead_id=None,
            lote_id=self._lote_id, gratis=self._costo_unitario == 0))
        if self._error is not None:
            raise self._error
        del_pais = tuple(e for e in self._empresas if e.pais == criterios.pais)
        return PaginaEmpresas(empresas=del_pais if pagina == 1 else (), total=len(del_pais))


class FabricaFalsa:
    """FabricaFuentes de prueba: arma una FuenteFalsa por entrada con el lote_id que le pasan y anota cada llamada.
    `metas` fija las fuentes y su orden; `empresas`, `errores` y `gasto` (lo que de verdad cuesta su llamada, a valor de
    lista; por defecto 0) van por clave."""

    def __init__(self, costos: RegistroCostosFalso, metas: Mapping[str, MetaFuente],
                 empresas: Mapping[str, tuple[EmpresaCruda, ...]] | None = None,
                 errores: Mapping[str, Exception] | None = None, gasto: Mapping[str, Decimal] | None = None):
        self.llamadas: list[UUID | None] = []  # lote_id de cada llamada
        self.criterios_por_fuente: dict[str, CriteriosICP] = {}  # clave -> lo que recibió su buscar()
        self._costos = costos
        self._metas = metas
        self._empresas = empresas or {}
        self._errores = errores or {}
        self._gasto = gasto or {}

    def __call__(self, lote_id: UUID) -> Mapping[str, FuenteFalsa]:
        self.llamadas.append(lote_id)
        return {clave: FuenteFalsa(meta, self._costos, lote_id, self._empresas.get(clave, ()), self._errores.get(clave),
                                  self.criterios_por_fuente, self._gasto.get(clave, Decimal(0)))
                for clave, meta in self._metas.items()}


LIMITE_FILAS_CALIFICADOR = 1000  # igual que DaptaCSV (plan.md): la suite de contrato exige el mismo límite


class CalificadorFalso:
    """Doble del puerto `Calificador`: mismo contrato que `DaptaCSV`, pero decodifica JSON en vez de CSV
    (tests/contratos/test_calificador.py prueba que ambos se comportan igual ante los mismos datos)."""

    def leer_resultados(self, archivo: bytes) -> list[ResultadoCalificacion | FilaRechazada]:
        filas = json.loads(archivo.decode("utf-8"))
        if len(filas) > LIMITE_FILAS_CALIFICADOR:
            raise ArchivoInvalido(f"más de {LIMITE_FILAS_CALIFICADOR} filas")
        ahora = datetime.now(UTC)
        return [mapear_fila(i, {k: str(v) for k, v in fila.items()}, ahora) for i, fila in enumerate(filas, start=1)]


class RepositorioCalificacionesFalso:
    """Repo en memoria: calificación y costo "en la misma transacción" (los dos se escriben juntos o ninguno).
    `estados` simula lo que decidiría Postgres para un `lead_id` dado; sin entrada, se asume `importada`."""

    def __init__(self, costos: RegistroCostosFalso, estados: dict[UUID, str] | None = None):
        self._costos = costos
        self._estados = estados or {}
        self.guardadas: list[ResultadoCalificacion] = []

    def guardar(self, resultado: ResultadoCalificacion, costo: OperacionCosto) -> str:
        estado = self._estados.get(resultado.lead_id, "importada")
        if estado == "importada":
            self.guardadas.append(resultado)
            self._costos.registrar(costo)
        return estado
