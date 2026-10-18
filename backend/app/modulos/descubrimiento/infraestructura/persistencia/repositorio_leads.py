import json
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import unidad_de_trabajo
from app.modulos.descubrimiento.dominio.errores import ErrorPersistencia
from app.modulos.descubrimiento.dominio.modelos import (
    CriteriosICP, EmpresaCruda, Lead, LeadParaEnriquecer, ResultadoEnriquecimiento)
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

_UPDATE_ENRIQUECIMIENTO = text(
    "UPDATE leads SET tipo_titular = :tipo_titular, contactable = :contactable, razon_no_contactable = :razon, "
    "encaje = :encaje, enriquecido_en = now(), "
    "telefono_cifrado = :telefono, telefono_canal = :telefono_canal, email_cifrado = :email, email_canal = :email_canal, "
    "nombre = CASE WHEN CAST(:claro AS boolean) THEN :nombre ELSE nombre END, "
    "direccion = CASE WHEN CAST(:claro AS boolean) THEN :direccion ELSE direccion END, "
    "nombre_cifrado = CASE WHEN CAST(:claro AS boolean) THEN NULL ELSE nombre_cifrado END, "
    "direccion_cifrada = CASE WHEN CAST(:claro AS boolean) THEN NULL ELSE direccion_cifrada END "
    "WHERE id = :id"
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

    def sin_enriquecer(self, busqueda_id: UUID) -> list[LeadParaEnriquecer]:
        with self._uow() as c:
            filas = c.execute(text(
                "SELECT DISTINCT l.id, l.tipo_titular, l.nombre, l.nombre_cifrado, l.ciudad, l.web, l.actividad_codigo, "
                "b.descripcion_icp, l.creado_en FROM leads l "
                "JOIN lead_fuentes lf ON lf.lead_id = l.id JOIN busquedas b ON b.id = lf.busqueda_id "
                "WHERE lf.busqueda_id = :b AND l.enriquecido_en IS NULL ORDER BY l.creado_en, l.id"),
                {"b": busqueda_id}).all()
        return [LeadParaEnriquecer(
            id=f.id, tipo_titular=f.tipo_titular, ciudad=f.ciudad, web=f.web, actividad=f.actividad_codigo,
            descripcion_icp=f.descripcion_icp,
            nombre=f.nombre if f.nombre is not None else self._cifrador.descifrar(
                "nombre_cifrado", bytes(f.nombre_cifrado), self._tenant_id, f.id)) for f in filas]

    def guardar_enriquecimiento(self, lead_id: UUID, r: ResultadoEnriquecimiento) -> None:
        cifrar = lambda columna, contacto: (  # noqa: E731
            None if contacto is None else self._cifrador.cifrar(columna, contacto[0], self._tenant_id, lead_id))
        with self._uow() as c:
            f = c.execute(text("SELECT tipo_titular, nombre_cifrado, direccion_cifrada FROM leads WHERE id = :id FOR UPDATE"),
                          {"id": lead_id}).one_or_none()
            if f is None:  # otro tenant o inexistente: RLS lo esconde
                raise ErrorPersistencia("el lead no existe")
            # Sube a jurídica: nombre y dirección pasan a claro (dato de empresa) y queda la constancia sin datos.
            claro = r.tipo_titular == "juridica" and f.tipo_titular != "juridica"
            descifrar = lambda columna, blob: (  # noqa: E731
                None if not claro or blob is None else self._cifrador.descifrar(columna, bytes(blob), self._tenant_id, lead_id))
            c.execute(_UPDATE_ENRIQUECIMIENTO, {
                "id": lead_id, "tipo_titular": r.tipo_titular, "contactable": r.contactable,
                "razon": r.razon_no_contactable, "encaje": r.encaje, "claro": claro,
                "nombre": descifrar("nombre_cifrado", f.nombre_cifrado),
                "direccion": descifrar("direccion_cifrada", f.direccion_cifrada),
                "telefono": cifrar("telefono_cifrado", r.telefono), "telefono_canal": r.telefono and r.telefono[1],
                "email": cifrar("email_cifrado", r.email), "email_canal": r.email and r.email[1],
            })
            if claro:
                c.execute(text(
                    "UPDATE cumplimiento SET solicitudes = solicitudes || jsonb_build_array(jsonb_build_object("
                    "'tipo', 'paso_a_claro', 'motivo', 'match_unico', 'fuente', 'croma_rues_co', 'ts', now())) "
                    "WHERE lead_id = :id"), {"id": lead_id})
