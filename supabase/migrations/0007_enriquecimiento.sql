-- 0007_enriquecimiento.sql — aprobada por Daniel (2026-10-18)

-- encaje y contactable viven en leads: son uno por lead, igual que tipo_titular.
ALTER TABLE public.leads
  ADD COLUMN contactable          boolean     NOT NULL DEFAULT false,
  ADD COLUMN razon_no_contactable text        NULL,
  ADD COLUMN encaje               text        NULL,
  ADD COLUMN enriquecido_en       timestamptz NULL,
  -- P3 (decidido): contacto cifrado como nombre/direccion en la 0003. La app cifra (AES-GCM); SQL no.
  ADD COLUMN telefono_cifrado     bytea       NULL,
  ADD COLUMN email_cifrado        bytea       NULL,
  ADD COLUMN telefono_canal       text        NULL,
  ADD COLUMN email_canal          text        NULL;

ALTER TABLE public.leads
  ADD CONSTRAINT leads_razon_no_contactable_enum
    CHECK (razon_no_contactable IN ('persona_natural','sin_canal_publicado','contacto_nominal')),
  -- contactable nunca lleva razón.
  ADD CONSTRAINT leads_contactable_sin_razon
    CHECK (NOT contactable OR razon_no_contactable IS NULL),
  -- Sin enriquecer se permite "false sin razón" (los defaults sobre filas existentes);
  -- enriquecido, o es contactable o tiene razón. La igualdad estricta rompería el ALTER (23514).
  ADD CONSTRAINT leads_enriquecido_con_veredicto
    CHECK (enriquecido_en IS NULL OR contactable OR razon_no_contactable IS NOT NULL),
  ADD CONSTRAINT leads_encaje_enum
    CHECK (encaje IN ('encaja','no_encaja','ninguna')),
  -- Mismo criterio que la 0003: nonce de 12 + etiqueta GCM de 16; un bytea más corto no es un cifrado.
  ADD CONSTRAINT leads_telefono_cifrado_ck
    CHECK (telefono_cifrado IS NULL OR octet_length(telefono_cifrado) > 28),
  ADD CONSTRAINT leads_email_cifrado_ck
    CHECK (email_cifrado IS NULL OR octet_length(email_cifrado) > 28),
  ADD CONSTRAINT leads_telefono_canal_enum
    CHECK (telefono_canal IN ('whatsapp_comercial','sitio_web','osm_contacto','whatsapp_osm')),
  -- Un email solo sale del sitio propio o de un tag de OSM: los canales whatsapp no aplican.
  ADD CONSTRAINT leads_email_canal_enum
    CHECK (email_canal IN ('sitio_web','osm_contacto')),
  -- La etiqueta sin dato (o el dato sin etiqueta) es un estado roto.
  ADD CONSTRAINT leads_canal_con_dato
    CHECK ((telefono_canal IS NULL) = (telefono_cifrado IS NULL)
       AND (email_canal    IS NULL) = (email_cifrado    IS NULL));

-- P5 (decidido): la descripción del ICP vive en la búsqueda.
ALTER TABLE public.busquedas ADD COLUMN descripcion_icp text NULL;

-- sin_enriquecer() filtra por esto en cada corrida.
CREATE INDEX leads_sin_enriquecer ON public.leads (tenant_id) WHERE enriquecido_en IS NULL;

-- P2 (decidido): v_leads_icp la crea la 006. Una fila por aparición del lead en una fuente.
-- encaje IS NULL (sin enriquecer) sigue entrando: la 006 solo resta lo que jev marcó no_encaja.
CREATE VIEW public.v_leads_icp WITH (security_invoker = true) AS
  SELECT lf.fuente, lf.lead_id, lf.busqueda_id
  FROM public.lead_fuentes lf
  JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
  WHERE l.encaje IS DISTINCT FROM 'no_encaja';

-- v_tablero_fuentes: el SELECT de la 0006 tal cual (fuente, encontrados, unicos, fila TOTAL y HAVING)
-- y las columnas nuevas AL FINAL: CREATE OR REPLACE no deja reordenar, renombrar ni cambiar tipos.
-- El LEFT JOIN es 1:1 (cada lead_fuentes tiene un lead), así que count(*) no cambia.
-- icp y los contadores cuentan leads distintos del ICP (encaje distinto de no_encaja).
-- no_contactables_politica excluye sin_canal_publicado: no es política, es falta de canal.
-- Repetir security_invoker: si se omite, el REPLACE lo pierde.
CREATE OR REPLACE VIEW public.v_tablero_fuentes WITH (security_invoker = true) AS
  SELECT lf.fuente,
         count(*)                   AS encontrados,
         count(DISTINCT lf.lead_id) AS unicos,
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja')                       AS icp,
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.telefono_canal IS NOT NULL)                                 AS con_telefono,
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja' AND l.contactable)      AS contactables,
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.razon_no_contactable IN ('persona_natural','contacto_nominal')) AS no_contactables_politica
  FROM public.lead_fuentes lf
  LEFT JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
  GROUP BY lf.fuente
  UNION ALL
  SELECT 'TOTAL',
         count(*),
         count(DISTINCT lf.lead_id),
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'),
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja' AND l.telefono_canal IS NOT NULL),
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja' AND l.contactable),
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.razon_no_contactable IN ('persona_natural','contacto_nominal'))
  FROM public.lead_fuentes lf
  LEFT JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
  HAVING count(*) > 0;

-- v_atribuciones (0006) no cambia.

-- Los GRANT/REVOKE de la 0006 sobreviven al REPLACE; la vista nueva necesita los suyos.
-- Mismo bloque que la 0006: solo si existen los roles de Supabase (en vanilla no hay nada que revocar).
GRANT SELECT ON public.v_leads_icp, public.v_tablero_fuentes TO app_rt;
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON public.v_leads_icp, public.v_tablero_fuentes FROM anon, authenticated;
  END IF;
END
$$;
