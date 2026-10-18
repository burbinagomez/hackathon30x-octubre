import json
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import unidad_de_trabajo
from app.modulos.descubrimiento.dominio.errores import ErrorPersistencia
from app.modulos.descubrimiento.dominio.modelos import Borrador, CriteriosICP, EmpresaCruda, Lead
from app.seguridad.cifrado import Cifrador

_INSERT_LEAD = text(
    "INSERT INTO leads (id, tenant_id, pais, id_fiscal, nombre, nombre_cifrado, tipo_titular, ciudad, direccion, "
    "direccion_cifrada, actividad_codigo, actividad_sistema, web) "
    "VALUES (:id, :t, :pais, :id_fiscal, :nombre, :nombre_cifrado, :tipo_titular, :ciudad, :direccion, "
    ":direccion_cifrada, :codigo, :sistema, :web) "
    "ON CONFLICT (tenant_id, pais, id_fiscal) DO NOTHING RETURNING id"
)
_INSERT_CUMPLIMIENTO = text(
    "INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
    "VALUES (:t, :lead_id, :fuente, :licencia, :url_origen, :as_of)"
)


class RepositorioLeadsPostgres:
    """Cada método abre su propia unidad de trabajo con el tenant fijado: RLS filtra todo lo que toca."""

    def __init__(self, engine: Engine, tenant_id: UUID, cifrador: Cifrador):
        self._engine = engine
        self._tenant_id = tenant_id
        self._cifrador = cifrador

    def crear_busqueda(self, criterios: CriteriosICP) -> UUID:
        with self._uow() as c:
            return c.execute(
                text("INSERT INTO busquedas (tenant_id, pais, criterios) VALUES (:t, :pais, CAST(:criterios AS jsonb)) "
                     "RETURNING id"),
                {"t": self._tenant_id, "pais": criterios.pais, "criterios": json.dumps(dict(criterios.filtros))},
            ).scalar_one()

    def crear_borrador(self, criterios: CriteriosICP, canal_preferido: str | None, tope_gasto_usd: Decimal,
                       mensaje_base: str | None) -> UUID:
        with self._uow() as c:
            return c.execute(
                text("INSERT INTO busquedas (tenant_id, pais, criterios, estado, canal_preferido, tope_gasto_usd, "
                     "mensaje_base) VALUES (:t, :pais, CAST(:criterios AS jsonb), 'borrador', :canal, :tope, :mensaje) "
                     "RETURNING id"),
                {"t": self._tenant_id, "pais": criterios.pais, "criterios": json.dumps(dict(criterios.filtros)),
                 "canal": canal_preferido, "tope": tope_gasto_usd, "mensaje": mensaje_base},
            ).scalar_one()

    def estado(self, busqueda_id: UUID) -> str | None:
        with self._uow() as c:  # RLS: la de otro tenant no aparece
            return c.execute(text("SELECT estado FROM busquedas WHERE id = :id"), {"id": busqueda_id}).scalar_one_or_none()

    def obtener_borrador(self, busqueda_id: UUID) -> Borrador | None:
        with self._uow() as c:
            f = c.execute(
                text("SELECT pais, criterios, canal_preferido, tope_gasto_usd, mensaje_base FROM busquedas "
                     "WHERE id = :id AND estado = 'borrador'"), {"id": busqueda_id}).one_or_none()
        if f is None:
            return None
        # JSON no distingue tupla de lista: las listas vuelven a ser tuplas (varios valores de un filtro).
        filtros = {k: tuple(v) if isinstance(v, list) else v for k, v in f.criterios.items()}
        return Borrador(id=busqueda_id, criterios=CriteriosICP(f.pais, filtros), canal_preferido=f.canal_preferido,
                        tope_gasto_usd=Decimal(f.tope_gasto_usd), mensaje_base=f.mensaje_base)

    def pasar_a_ejecutando(self, busqueda_id: UUID) -> bool:
        with self._uow() as c:
            return c.execute(
                text("UPDATE busquedas SET estado = 'ejecutando' WHERE id = :id AND estado = 'borrador'"),
                {"id": busqueda_id}).rowcount == 1

    @contextmanager
    def _uow(self) -> Iterator[Connection]:
        # El mensaje de Postgres trae la fila entera en el DETAIL (nombre, dirección): no sale de acá, ni como causa.
        try:
            with unidad_de_trabajo(self._engine, self._tenant_id) as c:
                yield c
        except DBAPIError:
            raise ErrorPersistencia("la base rechazó la operación") from None

    def _identidad(self, e: EmpresaCruda, lead_id: UUID) -> dict:
        """Nombre y dirección: en claro solo para una jurídica; para cualquier otro titular, cifrados (el CHECK lo exige)."""
        if e.tipo_titular == "juridica":
            return {"nombre": e.nombre, "direccion": e.direccion, "nombre_cifrado": None, "direccion_cifrada": None}
        cifrar = lambda columna, valor: (  # noqa: E731
            None if valor is None else self._cifrador.cifrar(columna, valor, self._tenant_id, lead_id))
        return {"nombre": None, "direccion": None, "nombre_cifrado": cifrar("nombre_cifrado", e.nombre),
                "direccion_cifrada": cifrar("direccion_cifrada", e.direccion)}

    def obtener_o_crear_lead(self, e: EmpresaCruda, licencia: str) -> tuple[UUID, bool]:
        # ponytail: id_fiscal NULL (OSM) no choca con el UNIQUE, así que siempre crea lead nuevo; dedup difuso en Pulido.
        with self._uow() as c:
            # El id lo genera la app: entra al AAD del cifrado, y la base no puede ponerlo después.
            # Si el INSERT choca con ON CONFLICT, este id se descarta.
            lead_id = uuid4()
            nuevo = c.execute(_INSERT_LEAD, {
                "id": lead_id, "t": self._tenant_id, "pais": e.pais, "id_fiscal": e.id_fiscal,
                "tipo_titular": e.tipo_titular, "ciudad": e.ciudad,
                "codigo": e.actividad.codigo, "sistema": e.actividad.sistema, "web": e.web,
                **self._identidad(e, lead_id),
            }).scalar_one_or_none()
            if nuevo is None:
                existente = c.execute(
                    text("SELECT id FROM leads WHERE pais = :pais AND id_fiscal = :id_fiscal"),
                    {"pais": e.pais, "id_fiscal": e.id_fiscal},
                ).scalar_one()
                return existente, False
            c.execute(_INSERT_CUMPLIMIENTO, {
                "t": self._tenant_id, "lead_id": nuevo, "fuente": e.fuente, "licencia": licencia,
                "url_origen": e.url_origen, "as_of": e.as_of,
            })
            return nuevo, True

    def agregar_lead_fuente(self, lead_id: UUID, busqueda_id: UUID, e: EmpresaCruda, licencia: str) -> None:
        with self._uow() as c:
            c.execute(
                text("INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                     "VALUES (:t, :lead_id, :busqueda_id, :fuente, :url_origen, :licencia) "
                     "ON CONFLICT (lead_id, fuente, busqueda_id) DO NOTHING"),
                {"t": self._tenant_id, "lead_id": lead_id, "busqueda_id": busqueda_id, "fuente": e.fuente,
                 "url_origen": e.url_origen, "licencia": licencia},
            )

    def obtener_lead(self, lead_id: UUID) -> Lead | None:
        with self._uow() as c:
            f = c.execute(
                text("SELECT pais, tipo_titular, id_fiscal, ciudad, web, nombre, direccion, nombre_cifrado, direccion_cifrada "
                     "FROM leads WHERE id = :id"), {"id": lead_id}).one_or_none()
        if f is None:
            return None
        descifrar = lambda columna, blob: (  # noqa: E731
            None if blob is None else self._cifrador.descifrar(columna, bytes(blob), self._tenant_id, lead_id))
        return Lead(id=lead_id, pais=f.pais, tipo_titular=f.tipo_titular, id_fiscal=f.id_fiscal, ciudad=f.ciudad, web=f.web,
                    nombre=f.nombre if f.nombre is not None else descifrar("nombre_cifrado", f.nombre_cifrado),
                    direccion=f.direccion if f.direccion is not None else descifrar("direccion_cifrada", f.direccion_cifrada))

    def cerrar_busqueda(self, busqueda_id: UUID, estado: str) -> None:
        with self._uow() as c:
            c.execute(text("UPDATE busquedas SET estado = :estado WHERE id = :id"), {"estado": estado, "id": busqueda_id})
