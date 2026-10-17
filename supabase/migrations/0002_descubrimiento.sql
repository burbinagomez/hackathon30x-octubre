-- 002: descubrimiento y libro de costos. SQL a mano. Corre como postgres (dueño).

CREATE TABLE public.tenants (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre    text NOT NULL,
  idioma    text NOT NULL DEFAULT 'es' CHECK (idioma IN ('es', 'en')),
  creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.busquedas (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES public.tenants(id),
  pais            text NOT NULL,
  criterios       jsonb NOT NULL,
  estado          text NOT NULL DEFAULT 'creada' CHECK (estado IN ('creada', 'terminada', 'con_errores')),
  canal_preferido text,
  tope_gasto_usd  numeric,
  mensaje_base    text
);

CREATE TABLE public.leads (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES public.tenants(id),
  pais              text NOT NULL,
  id_fiscal         text,
  nombre            text NOT NULL,
  tipo_titular      text NOT NULL DEFAULT 'desconocido' CHECK (tipo_titular IN ('juridica', 'natural', 'desconocido')),
  ciudad            text,
  direccion         text,
  actividad_codigo  text,
  actividad_sistema text,
  web               text,
  -- El idioma del mensaje sale del país, nunca de la UI. País sin rama: NULL.
  idioma_contacto   text GENERATED ALWAYS AS (
    CASE pais WHEN 'CO' THEN 'es' WHEN 'MX' THEN 'es' WHEN 'PE' THEN 'es' WHEN 'BR' THEN 'pt' END
  ) STORED,
  CONSTRAINT leads_tenant_pais_id_fiscal_key UNIQUE (tenant_id, pais, id_fiscal)
);

CREATE TABLE public.lead_fuentes (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES public.tenants(id),
  lead_id       uuid NOT NULL REFERENCES public.leads(id),
  busqueda_id   uuid NOT NULL REFERENCES public.busquedas(id),
  fuente        text NOT NULL,
  encontrado_en timestamptz NOT NULL DEFAULT now(),
  url_origen    text NOT NULL,
  licencia      text NOT NULL,
  CONSTRAINT lead_fuentes_lead_fuente_busqueda_key UNIQUE (lead_id, fuente, busqueda_id)
);

CREATE TABLE public.cumplimiento (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES public.tenants(id),
  lead_id     uuid NOT NULL REFERENCES public.leads(id),
  fuente      text NOT NULL,
  licencia    text NOT NULL,
  url_origen  text NOT NULL,
  base_legal  text,  -- la setea AprobarMensaje en el 007
  as_of       timestamptz NOT NULL,
  opt_out_at  timestamptz,
  solicitudes jsonb NOT NULL DEFAULT '[]'::jsonb,
  CONSTRAINT cumplimiento_lead_id_key UNIQUE (lead_id)
);

-- lead_id y lote_id sin FK: un costo no se pierde porque se borre un lead.
CREATE TABLE public.costos (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES public.tenants(id),
  tipo           text NOT NULL CHECK (tipo IN (
                   'socrata_descarga', 'overpass_query', 'web_fetch', 'llm_tokens_in', 'llm_tokens_out',
                   'jev_tokens', 'croma_consulta', 'email_envio', 'whatsapp_plantilla', 'dapta_llamada',
                   'minutos_humanos')),
  unidades       numeric NOT NULL,
  costo_unitario numeric NOT NULL,
  moneda         text NOT NULL,
  proveedor      text NOT NULL,
  fuente         text,
  canal          text,
  lead_id        uuid,
  lote_id        uuid,
  gratis         boolean NOT NULL,
  ts             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX costos_tenant_proveedor_ts_idx ON public.costos (tenant_id, proveedor, ts);

-- Global, sin tenant_id: datos públicos de gobierno. No se expone por API (Croma no se redistribuye).
CREATE TABLE public.fuente_cache (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proveedor   text NOT NULL,
  endpoint    text NOT NULL,
  hash_params text NOT NULL,
  respuesta   jsonb NOT NULL,
  as_of       timestamptz NOT NULL,
  CONSTRAINT fuente_cache_proveedor_endpoint_hash_key UNIQUE (proveedor, endpoint, hash_params)
);

GRANT SELECT ON public.tenants TO app_rt;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.busquedas, public.leads, public.lead_fuentes,
  public.cumplimiento, public.costos TO app_rt;
GRANT SELECT, INSERT, UPDATE ON public.fuente_cache TO app_rt;
