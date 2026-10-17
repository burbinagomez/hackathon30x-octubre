from uuid import UUID, uuid4

from sqlalchemy import Engine

from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, EmpresaCruda


class RepositorioLeadsPostgres:
    """Cada método abre su propia unidad de trabajo con el tenant fijado. Esqueleto de T020: el Verde es T021."""

    def __init__(self, engine: Engine, tenant_id: UUID):
        self._engine = engine
        self._tenant_id = tenant_id

    def crear_busqueda(self, criterios: CriteriosICP) -> UUID:
        return uuid4()

    def obtener_o_crear_lead(self, e: EmpresaCruda, licencia: str) -> tuple[UUID, bool]:
        return uuid4(), True

    def agregar_lead_fuente(self, lead_id: UUID, busqueda_id: UUID, e: EmpresaCruda, licencia: str) -> None:
        return None

    def cerrar_busqueda(self, busqueda_id: UUID, estado: str) -> None:
        return None
