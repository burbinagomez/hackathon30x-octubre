from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Sin importar config: el drift check (test_migraciones) lo carga sin el entorno de api.
# Espejo de supabase/migrations/: la fuente de verdad es el SQL; esto solo existe para compare_metadata.
metadata = MetaData()

_UUID_PK = dict(primary_key=True, server_default=text("gen_random_uuid()"))
_AHORA = text("now()")


def _id() -> Column:
    return Column("id", UUID(as_uuid=True), **_UUID_PK)


def _tenant() -> Column:
    return Column("tenant_id", UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)


tenants = Table(
    "tenants", metadata,
    _id(),
    Column("nombre", Text, nullable=False),
    Column("idioma", Text, nullable=False, server_default=text("'es'::text")),
    Column("creado_en", DateTime(timezone=True), nullable=False, server_default=_AHORA),
)

busquedas = Table(
    "busquedas", metadata,
    _id(), _tenant(),
    Column("pais", Text, nullable=False),
    Column("criterios", JSONB, nullable=False),
    Column("estado", Text, nullable=False, server_default=text("'creada'::text")),
    Column("canal_preferido", Text),
    Column("tope_gasto_usd", Numeric),
    Column("mensaje_base", Text),
    Column("creado_en", DateTime(timezone=True), nullable=False, server_default=_AHORA),
    UniqueConstraint("tenant_id", "id", name="busquedas_tenant_id_id_key"),
)

leads = Table(
    "leads", metadata,
    _id(), _tenant(),
    Column("pais", Text, nullable=False),
    Column("id_fiscal", Text),
    Column("nombre", Text, nullable=False),
    Column("tipo_titular", Text, nullable=False, server_default=text("'desconocido'::text")),
    Column("ciudad", Text),
    Column("direccion", Text),
    Column("actividad_codigo", Text),
    Column("actividad_sistema", Text),
    Column("web", Text),
    Column("idioma_contacto", Text, Computed(
        "CASE pais WHEN 'CO' THEN 'es' WHEN 'MX' THEN 'es' WHEN 'PE' THEN 'es' WHEN 'BR' THEN 'pt' END",
        persisted=True,
    )),
    Column("creado_en", DateTime(timezone=True), nullable=False, server_default=_AHORA),
    UniqueConstraint("tenant_id", "pais", "id_fiscal", name="leads_tenant_pais_id_fiscal_key"),
    UniqueConstraint("tenant_id", "id", name="leads_tenant_id_id_key"),
)

lead_fuentes = Table(
    "lead_fuentes", metadata,
    _id(), _tenant(),
    Column("lead_id", UUID(as_uuid=True), nullable=False),
    Column("busqueda_id", UUID(as_uuid=True), nullable=False),
    Column("fuente", Text, nullable=False),
    Column("encontrado_en", DateTime(timezone=True), nullable=False, server_default=_AHORA),
    Column("url_origen", Text, nullable=False),
    Column("licencia", Text, nullable=False),
    UniqueConstraint("lead_id", "fuente", "busqueda_id", name="lead_fuentes_lead_fuente_busqueda_key"),
    ForeignKeyConstraint(["tenant_id", "lead_id"], ["leads.tenant_id", "leads.id"]),
    ForeignKeyConstraint(["tenant_id", "busqueda_id"], ["busquedas.tenant_id", "busquedas.id"]),
)

cumplimiento = Table(
    "cumplimiento", metadata,
    _id(), _tenant(),
    Column("lead_id", UUID(as_uuid=True), nullable=False),
    Column("fuente", Text, nullable=False),
    Column("licencia", Text, nullable=False),
    Column("url_origen", Text, nullable=False),
    Column("base_legal", Text),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("opt_out_at", DateTime(timezone=True)),
    Column("solicitudes", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    UniqueConstraint("lead_id", name="cumplimiento_lead_id_key"),
    ForeignKeyConstraint(["tenant_id", "lead_id"], ["leads.tenant_id", "leads.id"]),
)

costos = Table(
    "costos", metadata,
    _id(), _tenant(),
    Column("tipo", Text, nullable=False),
    Column("unidades", Numeric, nullable=False),
    Column("costo_unitario", Numeric, nullable=False),
    Column("moneda", Text, nullable=False),
    Column("proveedor", Text, nullable=False),
    Column("fuente", Text),
    Column("canal", Text),
    Column("lead_id", UUID(as_uuid=True)),
    Column("lote_id", UUID(as_uuid=True)),
    Column("gratis", Boolean, nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False, server_default=_AHORA),
    Index("costos_tenant_proveedor_ts_idx", "tenant_id", "proveedor", "ts"),
)

fuente_cache = Table(
    "fuente_cache", metadata,
    _id(),
    Column("proveedor", Text, nullable=False),
    Column("endpoint", Text, nullable=False),
    Column("hash_params", Text, nullable=False),
    Column("respuesta", JSONB, nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    UniqueConstraint("proveedor", "endpoint", "hash_params", name="fuente_cache_proveedor_endpoint_hash_key"),
)
