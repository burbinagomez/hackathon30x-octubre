import json
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import unidad_de_trabajo
from app.modulos.descubrimiento.dominio.errores import ErrorPersistencia
from app.modulos.descubrimiento.dominio.modelos import (
    Borrador,
    CriteriosICP,
    EmpresaCruda,
    AtribucionFuente,
    Lead,
    LeadParaEnriquecer,
    LeadListado,
    PaginaLeads,
    ResultadoEnriquecimiento,
    ResumenBusqueda,
)
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
    # COALESCE: un contacto ya guardado (p. ej. el de OSM, T040p) nunca se pisa con NULL.
    "telefono_cifrado = COALESCE(:telefono, telefono_cifrado), telefono_canal = COALESCE(:telefono_canal, telefono_canal), "
    "email_cifrado = COALESCE(:email, email_cifrado), email_canal = COALESCE(:email_canal, email_canal), "
    "nombre = CASE WHEN CAST(:claro AS boolean) THEN :nombre ELSE nombre END, "
    "direccion = CASE WHEN CAST(:claro AS boolean) THEN :direccion ELSE direccion END, "
    "nombre_cifrado = CASE WHEN CAST(:claro AS boolean) THEN NULL ELSE nombre_cifrado END, "
    "direccion_cifrada = CASE WHEN CAST(:claro AS boolean) THEN NULL ELSE direccion_cifrada END "
    "WHERE id = :id"
)


# Lectura para la pantalla de leads. Departamento y ciudad de la búsqueda salen de los criterios guardados.
_SQL_BUSQUEDAS = text("""
    SELECT b.id, b.creado_en, b.estado, b.pais, b.criterios->>'departamento' AS departamento,
           b.criterios->>'ciudad' AS ciudad,
           (SELECT count(DISTINCT lf.lead_id) FROM lead_fuentes lf WHERE lf.busqueda_id = b.id) AS total_leads
    FROM busquedas b ORDER BY b.creado_en DESC, b.id""")
# Una sola consulta con tres alcances (una búsqueda, una fuente en todas las búsquedas, o todo): cambia solo el filtro.
# Los filtros son constantes de este módulo, nunca texto del request; el valor viaja como parámetro.
_FILTRO_BUSQUEDA = "lf.busqueda_id = :b"
_FILTRO_FUENTE = "l.id IN (SELECT lead_id FROM lead_fuentes WHERE fuente = :f)"
_FILTRO_TODOS = "TRUE"
# Solo jurídicas, con teléfono o correo guardado. Constante del módulo; se agrega con AND al filtro de alcance.
_CON_CONTACTO = "l.tipo_titular = 'juridica' AND (l.telefono_cifrado IS NOT NULL OR l.email_cifrado IS NOT NULL)"
_DESDE = "FROM leads l JOIN lead_fuentes lf ON lf.lead_id = l.id WHERE "


def _sql_total(filtro: str):
    return text(f"SELECT count(DISTINCT l.id) {_DESDE}{filtro}")


def _sql_leads(filtro: str):
    return text(f"""
    SELECT l.id, CASE WHEN l.tipo_titular = 'juridica' THEN l.nombre END AS nombre, l.tipo_titular, l.ciudad,
           l.web IS NOT NULL AS tiene_web,
           -- Solo el IS NOT NULL: nunca se lee ni descifra el contacto. Natural o desconocido: NULL (no se expone nada).
           CASE WHEN l.tipo_titular = 'juridica' THEN l.telefono_cifrado IS NOT NULL END AS tiene_telefono,
           CASE WHEN l.tipo_titular = 'juridica' THEN l.email_cifrado IS NOT NULL END AS tiene_email,
           array_agg(lf.fuente ORDER BY lf.fuente) AS fuentes,
           array_agg(lf.licencia ORDER BY lf.fuente) AS licencias
    {_DESDE}{filtro}
    GROUP BY l.id ORDER BY l.creado_en, l.id LIMIT :limite OFFSET :desde""")


def _sql_atribuciones(filtro: str):
    return text(f"""
    SELECT a.fuente, a.texto, a.url FROM v_atribuciones a
    WHERE a.fuente IN (SELECT lf.fuente {_DESDE}{filtro}) ORDER BY a.orden""")


class RepositorioLeadsPostgres:
    """Cada método abre su propia unidad de trabajo con el tenant fijado: RLS filtra todo lo que toca."""

    def __init__(self, engine: Engine, tenant_id: UUID, cifrador: Cifrador):
        self._engine = engine
        self._tenant_id = tenant_id
        self._cifrador = cifrador
        self._compartida: Connection | None = None  # la conexión de `transaccion()`; None fuera de ella

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
    def transaccion(self) -> Iterator[None]:
        """Los métodos de escritura de adentro comparten esta transacción (en vez de una cada uno)."""
        with self._uow() as c:
            self._compartida = c
            try:
                yield
            finally:
                self._compartida = None

    @contextmanager
    def savepoint(self) -> Iterator[None]:
        """SAVEPOINT: si lo de adentro lanza, vuelve a él y la transacción sigue viva para la próxima fuente."""
        assert self._compartida is not None, "savepoint() va dentro de transaccion()"
        with self._compartida.begin_nested():
            yield

    @contextmanager
    def _uow(self) -> Iterator[Connection]:
        if self._compartida is not None:
            try:
                yield self._compartida
            except DBAPIError:
                raise ErrorPersistencia("la base rechazó la operación") from None
            return
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
        contacto = lambda columna, blob, canal, lead_id: (  # noqa: E731  el que ya trae el lead compite con el del sitio
            None if blob is None else (self._cifrador.descifrar(columna, bytes(blob), self._tenant_id, lead_id), canal))
        with self._uow() as c:
            filas = c.execute(text(
                "SELECT DISTINCT l.id, l.tipo_titular, l.nombre, l.nombre_cifrado, l.ciudad, l.web, l.actividad_codigo, "
                "l.telefono_cifrado, l.telefono_canal, l.email_cifrado, l.email_canal, b.descripcion_icp, l.creado_en FROM leads l "
                "JOIN lead_fuentes lf ON lf.lead_id = l.id JOIN busquedas b ON b.id = lf.busqueda_id "
                "WHERE lf.busqueda_id = :b AND l.enriquecido_en IS NULL ORDER BY l.creado_en, l.id"),
                {"b": busqueda_id}).all()
        return [LeadParaEnriquecer(
            id=f.id, tipo_titular=f.tipo_titular, ciudad=f.ciudad, web=f.web, actividad=f.actividad_codigo,
            descripcion_icp=f.descripcion_icp,
            telefono=contacto("telefono_cifrado", f.telefono_cifrado, f.telefono_canal, f.id),
            email=contacto("email_cifrado", f.email_cifrado, f.email_canal, f.id),
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

    def listar_busquedas(self) -> list[ResumenBusqueda]:
        """Solo lectura; el tenant lo filtra la RLS (sin WHERE tenant_id a propósito: el test lo sabotea)."""
        with self._uow() as c:
            filas = c.execute(_SQL_BUSQUEDAS).all()
        return [ResumenBusqueda(id=f.id, creada_en=f.creado_en, estado=f.estado, pais=f.pais, departamento=f.departamento,
                                ciudad=f.ciudad, total_leads=f.total_leads) for f in filas]

    def listar_leads(self, busqueda_id: UUID, pagina: int, tamano: int, con_contacto: bool = False) -> PaginaLeads | None:
        """None si la búsqueda no existe para este tenant."""
        with self._uow() as c:
            if c.execute(text("SELECT 1 FROM busquedas WHERE id = :id"), {"id": busqueda_id}).first() is None:
                return None
            return self._pagina(c, _FILTRO_BUSQUEDA, {"b": busqueda_id}, pagina, tamano, con_contacto)

    def listar_leads_de_fuente(self, fuente: str | None, pagina: int, tamano: int,
                               con_contacto: bool = False) -> PaginaLeads:
        """Leads de una fuente en todas las búsquedas del tenant; sin fuente, todos. Que la fuente exista lo valida la API."""
        with self._uow() as c:
            if fuente is None:
                return self._pagina(c, _FILTRO_TODOS, {}, pagina, tamano, con_contacto)
            return self._pagina(c, _FILTRO_FUENTE, {"f": fuente}, pagina, tamano, con_contacto)

    @staticmethod
    def _pagina(c: Connection, filtro: str, params: dict, pagina: int, tamano: int,
                con_contacto: bool = False) -> PaginaLeads:
        """Nunca lee las columnas cifradas ni descifra: el nombre sale solo de una jurídica (el CASE lo repite aunque el
        CHECK ya lo garantice), y no hay dirección ni contacto: del teléfono y el correo solo se sabe si existen
        (IS NOT NULL, y solo de una jurídica). El tenant lo filtra la RLS."""
        if con_contacto:
            filtro = f"({filtro}) AND {_CON_CONTACTO}"
        total = c.execute(_sql_total(filtro), params).scalar_one()
        filas = c.execute(_sql_leads(filtro), {**params, "limite": tamano, "desde": (pagina - 1) * tamano}).all()
        atribuciones = c.execute(_sql_atribuciones(filtro), params).all()
        items = tuple(LeadListado(
            id=f.id, nombre=f.nombre, tipo_titular=f.tipo_titular, fuentes=tuple(f.fuentes), licencias=tuple(f.licencias),
            ciudad=f.ciudad, tiene_web=f.tiene_web,
            tiene_telefono=f.tiene_telefono, tiene_email=f.tiene_email) for f in filas)
        return PaginaLeads(items=items, total=total, pagina=pagina, tamano=tamano, atribuciones=tuple(
            AtribucionFuente(a.fuente, a.texto, a.url) for a in atribuciones))
