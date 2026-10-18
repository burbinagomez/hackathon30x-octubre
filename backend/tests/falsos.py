"""Falsos en memoria de los puertos. Mismo contrato que Postgres: dedup por (pais, id_fiscal), ON CONFLICT en lead_fuentes."""
from decimal import Decimal
from uuid import UUID, uuid4

from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, EmpresaCruda, MetaFuente, PaginaEmpresas
from app.modulos.enriquecimiento.dominio.puertos import Encaje
from app.modulos.enriquecimiento.infraestructura.adaptadores.jev_clasificador import (
    cuerpo_jev, operacion_jev, tokens_validos, validar_salida)
from app.modulos.enriquecimiento.dominio.errores import UsoJevInvalido


class RepositorioLeadsFalso:
    def __init__(self):
        self.busquedas: dict[UUID, str] = {}  # id -> estado
        self.leads: dict[tuple[str, str | None], UUID] = {}  # (pais, id_fiscal) -> id
        self.cumplimiento: dict[UUID, tuple] = {}  # lead_id -> (fuente, licencia, url_origen, as_of)
        self.lead_fuentes: set[tuple[UUID, str, UUID]] = set()  # (lead_id, fuente, busqueda_id)

    def crear_busqueda(self, criterios: CriteriosICP) -> UUID:
        busqueda_id = uuid4()
        self.busquedas[busqueda_id] = "creada"
        return busqueda_id

    def obtener_o_crear_lead(self, e: EmpresaCruda, licencia: str) -> tuple[UUID, bool]:
        clave = (e.pais, e.id_fiscal)
        if e.id_fiscal is not None and clave in self.leads:
            return self.leads[clave], False
        lead_id = uuid4()
        self.leads[clave if e.id_fiscal is not None else (e.pais, str(lead_id))] = lead_id
        self.cumplimiento[lead_id] = (e.fuente, licencia, e.url_origen, e.as_of)
        return lead_id, True

    def agregar_lead_fuente(self, lead_id: UUID, busqueda_id: UUID, e: EmpresaCruda, licencia: str) -> None:
        self.lead_fuentes.add((lead_id, e.fuente, busqueda_id))

    def cerrar_busqueda(self, busqueda_id: UUID, estado: str) -> None:
        self.busquedas[busqueda_id] = estado


class RegistroCostosFalso:
    def __init__(self, requests_24h: int = 0, creditos_mes: Decimal = Decimal(0)):
        self.filas: list[OperacionCosto] = []
        self._requests_24h = requests_24h
        self._creditos_mes = creditos_mes

    def registrar(self, op: OperacionCosto) -> None:
        self.filas.append(op)

    def requests_24h(self, proveedor: str) -> int:
        return self._requests_24h

    def creditos_mes(self, proveedor: str) -> Decimal:
        return self._creditos_mes

    def gasto_busqueda(self, busqueda_id: UUID) -> Decimal:
        return sum((op.unidades * op.costo_unitario for op in self.filas if op.lote_id == busqueda_id), Decimal(0))


class FuenteFalsa:
    """Escribe 1 fila de costos con su lote_id y devuelve sus empresas del país pedido en la página 1, o lanza `error`."""

    def __init__(self, meta: MetaFuente, costos: RegistroCostosFalso, lote_id: UUID,
                 empresas: tuple[EmpresaCruda, ...] = (), error: Exception | None = None):
        self.meta = meta
        self._costos = costos
        self._lote_id = lote_id
        self._empresas = empresas
        self._error = error

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        self._costos.registrar(OperacionCosto(
            tipo="web_fetch", unidades=Decimal(1), costo_unitario=Decimal(0), moneda="USD",
            proveedor=self.meta.proveedor, fuente=self.meta.clave, canal=None, lead_id=None,
            lote_id=self._lote_id, gratis=True))
        if self._error is not None:
            raise self._error
        del_pais = tuple(e for e in self._empresas if e.pais == criterios.pais)
        return PaginaEmpresas(empresas=del_pais if pagina == 1 else (), total=len(del_pais))


class JevFalso:
    """ClasificadorEncaje en memoria: valida y registra jev_tokens igual que JevClasificador, sin HTTP."""

    def __init__(self, salida: dict | None, costos: "RegistroCostosFalso", tokens_in: int = 500,
                 usd_in_por_M: Decimal = Decimal("0.042")):
        self.salida = salida or {"etiqueta": "encaja", "probabilidad": 0.9}
        self.costos = costos
        self.tokens_in = tokens_in
        self.usd_in_por_M = usd_in_por_M

    def clasificar(self, lead_id: UUID, descripcion_icp: str, nombre: str, ciudad: str | None,
                   actividad: str | None) -> Encaje:
        tokens = tokens_validos(self.tokens_in)
        techo = len(cuerpo_jev(descripcion_icp, nombre, ciudad, actividad))
        self.costos.registrar(operacion_jev(lead_id, techo if tokens is None else tokens, self.usd_in_por_M))
        if tokens is None:
            raise UsoJevInvalido
        return validar_salida(self.salida)
