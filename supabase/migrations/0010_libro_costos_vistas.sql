-- 0010: los cuerpos de las vistas del libro de costos (005 spec:334-354). SQL a mano. Corre como postgres (dueño).
-- Va después de la 0009. T008: la 0006 (el DDL [MIN] que aprobó el dueño, congelado por test_migracion_0006) solo trae
-- `v_tablero_fuentes` reducida (fuente, encontrados, unicos) y `v_atribuciones`; la 0008 (006) dejó `v_leads_icp` con el
-- filtro de encaje y las columnas de contacto del tablero. Acá van las 7 vistas que faltan y las columnas de costo del
-- tablero, AL FINAL: `CREATE OR REPLACE VIEW` acepta columnas nuevas al final y no deja reordenar ni renombrar las que ya están.
-- Todas con `security_invoker = true` (spec:334): sin la opción corren como su dueño (postgres, superusuario) y un tenant
-- vería los datos del otro. Es el aislamiento del principio III; la prueba de cada vista es de T009.

-- `fusionado_en`: el lead absorbido apunta al que lo absorbió (cola de dedup). FK simple acá; la compuesta
-- `(tenant_id, fusionado_en) → leads (tenant_id, id)` es de T011, después de su rojo.
ALTER TABLE public.leads ADD COLUMN fusionado_en uuid NULL REFERENCES public.leads(id);

-- v_costos: la única definición del filtro de evals (desarrollo). Las demás vistas de costo salen de acá.
-- `fuente_ef` = la fuente de la fila, con la fuente nula como `sin_atribuir` (spec:335).
CREATE VIEW public.v_costos WITH (security_invoker = true) AS
  SELECT id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, canal, lead_id, lote_id, gratis, ts,
         COALESCE(fuente, 'sin_atribuir') AS fuente_ef,
         unidades * costo_unitario AS monto_lista,
         CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END AS monto_real
  FROM public.costos
  WHERE fuente IS DISTINCT FROM 'evals';

-- v_costo_evals: lo de desarrollo queda aparte y no entra al costo de adquisición (spec:336, 119).
CREATE VIEW public.v_costo_evals WITH (security_invoker = true) AS
  SELECT lote_id, sum(unidades * costo_unitario) AS costo_lista,
         sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END) AS costo_real
  FROM public.costos WHERE fuente = 'evals' GROUP BY lote_id;

-- v_leads_icp: la única definición de ICP (spec:337). La 0008 le puso el filtro de encaje; acá suma `fusionado_en IS NULL`.
-- Repetir `security_invoker`: si se omite, el REPLACE lo pierde.
CREATE OR REPLACE VIEW public.v_leads_icp WITH (security_invoker = true) AS
  SELECT lf.fuente, lf.lead_id, lf.busqueda_id
  FROM public.lead_fuentes lf
  JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
  WHERE l.encaje IS DISTINCT FROM 'no_encaja' AND l.fusionado_en IS NULL;

-- v_prorrateo: las filas de lote (`lead_id IS NULL`, tenga o no `lote_id`) se reparten entre los leads del ICP de ESE lote
-- y ESA fuente (spec:338). Un grupo sin leads no aparece acá: es desperdicio. Sin `lote_id` no hay grupo, así que el JOIN
-- con el ICP lo descarta solo.
CREATE VIEW public.v_prorrateo WITH (security_invoker = true) AS
  WITH lote AS (
    SELECT lote_id, fuente_ef, sum(monto_lista) AS lista, sum(monto_real) AS real
    FROM public.v_costos WHERE lead_id IS NULL GROUP BY lote_id, fuente_ef),
  icp AS (SELECT busqueda_id AS lote_id, fuente, lead_id FROM public.v_leads_icp),
  divisor AS (SELECT lote_id, fuente, count(DISTINCT lead_id) AS n FROM icp GROUP BY lote_id, fuente)
  SELECT l.lote_id, l.fuente_ef AS fuente, i.lead_id,
         l.lista / d.n AS parte_lista, l.real / d.n AS parte_real
  FROM lote l
  JOIN divisor d ON d.lote_id = l.lote_id AND d.fuente = l.fuente_ef
  JOIN icp i ON i.lote_id = l.lote_id AND i.fuente = l.fuente_ef;

-- v_desperdicio: los grupos (lote, fuente) que no produjeron ningún lead del ICP (spec:339).
CREATE VIEW public.v_desperdicio WITH (security_invoker = true) AS
  WITH lote AS (
    SELECT lote_id, fuente_ef, sum(monto_lista) AS lista, sum(monto_real) AS real
    FROM public.v_costos WHERE lead_id IS NULL GROUP BY lote_id, fuente_ef),
  con_leads AS (SELECT DISTINCT busqueda_id AS lote_id, fuente FROM public.v_leads_icp)
  SELECT l.fuente_ef AS fuente, l.lote_id, l.lista AS desperdicio_lista, l.real AS desperdicio_real
  FROM lote l
  LEFT JOIN con_leads c ON c.lote_id = l.lote_id AND c.fuente = l.fuente_ef
  WHERE c.lote_id IS NULL;

-- v_costo_por_lead: el costo directo (fila con `lead_id`) más la parte prorrateada del lote (spec:340, 329).
CREATE VIEW public.v_costo_por_lead WITH (security_invoker = true) AS
  WITH directo AS (
    SELECT lead_id, fuente_ef AS fuente, sum(monto_lista) AS lista, sum(monto_real) AS real
    FROM public.v_costos WHERE lead_id IS NOT NULL GROUP BY lead_id, fuente_ef),
  partes AS (
    SELECT lead_id, fuente, sum(parte_lista) AS lista, sum(parte_real) AS real
    FROM public.v_prorrateo GROUP BY lead_id, fuente),
  todo AS (SELECT * FROM directo UNION ALL SELECT * FROM partes)
  SELECT lead_id, fuente, sum(lista) AS costo_lista, sum(real) AS costo_real
  FROM todo GROUP BY lead_id, fuente;

-- v_costo_por_canal: solo las filas con canal; una fila sin canal es de la fuente, no de un canal (spec:341).
CREATE VIEW public.v_costo_por_canal WITH (security_invoker = true) AS
  SELECT canal, sum(monto_lista) AS costo_lista, sum(monto_real) AS costo_real
  FROM public.v_costos WHERE canal IS NOT NULL GROUP BY canal;

-- v_tablero_fuentes: el cuerpo de la 0008 con `icp` leído del ICP (spec:337: la única definición) y las columnas de costo
-- al final (spec:342-348). `encontrados` y `unicos` siguen contando `lead_fuentes` tal cual (006 spec:97).
-- Las fuentes de `costos` entran aunque no tengan leads (la fuente nula es `sin_atribuir`), pero `intake` no: la
-- calibración de la Puerta B va aparte y no es costo de adquisición (lo exige `test_tablero_repo`).
-- `cpl` = costo / ICP con NULLIF: sin divisor queda NULL ("sin dato"), nunca 0 ni un error de división.
CREATE OR REPLACE VIEW public.v_tablero_fuentes WITH (security_invoker = true) AS
  WITH base AS (
    SELECT lf.fuente,
           count(*) AS encontrados,
           count(DISTINCT lf.lead_id) AS unicos,
           count(DISTINCT lf.lead_id) FILTER (WHERE i.lead_id IS NOT NULL) AS icp,
           count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.telefono_canal IS NOT NULL) AS con_telefono,
           count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.contactable) AS contactables,
           count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.razon_no_contactable IN ('persona_natural', 'contacto_nominal')) AS no_contactables_politica
    FROM public.lead_fuentes lf
    LEFT JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
    LEFT JOIN public.v_leads_icp i ON i.fuente = lf.fuente AND i.lead_id = lf.lead_id
                                 AND i.busqueda_id = lf.busqueda_id
    GROUP BY lf.fuente),
  costos AS (
    SELECT fuente_ef AS fuente, sum(monto_lista) AS lista, sum(monto_real) AS real
    FROM public.v_costos WHERE fuente_ef <> 'intake' GROUP BY fuente_ef),
  perdido AS (
    SELECT fuente, sum(desperdicio_lista) AS lista, sum(desperdicio_real) AS real
    FROM public.v_desperdicio GROUP BY fuente),
  filas AS (
    SELECT COALESCE(b.fuente, c.fuente) AS fuente, COALESCE(b.encontrados, 0) AS encontrados,
           COALESCE(b.unicos, 0) AS unicos, COALESCE(b.icp, 0) AS icp,
           COALESCE(b.con_telefono, 0) AS con_telefono, COALESCE(b.contactables, 0) AS contactables,
           COALESCE(b.no_contactables_politica, 0) AS no_contactables_politica,
           COALESCE(c.lista, 0) AS costo_lista, COALESCE(c.real, 0) AS costo_real,
           COALESCE(d.lista, 0) AS desperdicio_lista, COALESCE(d.real, 0) AS desperdicio_real
    FROM base b
    FULL JOIN costos c ON c.fuente = b.fuente
    LEFT JOIN perdido d ON d.fuente = COALESCE(b.fuente, c.fuente)),
  total AS (
    SELECT count(*) AS encontrados, count(DISTINCT lf.lead_id) AS unicos,
           count(DISTINCT lf.lead_id) FILTER (WHERE i.lead_id IS NOT NULL) AS icp,
           count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.telefono_canal IS NOT NULL) AS con_telefono,
           count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.contactable) AS contactables,
           count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.razon_no_contactable IN ('persona_natural', 'contacto_nominal')) AS no_contactables_politica,
           (SELECT sum(costo_lista) FROM filas) AS costo_lista,
           (SELECT sum(costo_real) FROM filas) AS costo_real,
           (SELECT sum(desperdicio_lista) FROM filas) AS desperdicio_lista,
           (SELECT sum(desperdicio_real) FROM filas) AS desperdicio_real
    FROM public.lead_fuentes lf
    LEFT JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
    LEFT JOIN public.v_leads_icp i ON i.fuente = lf.fuente AND i.lead_id = lf.lead_id
                                 AND i.busqueda_id = lf.busqueda_id
    HAVING count(*) > 0)
  SELECT fuente, encontrados, unicos, icp, con_telefono, contactables, no_contactables_politica,
         costo_lista, costo_real, desperdicio_lista, desperdicio_real,
         costo_lista / NULLIF(icp, 0) AS cpl_lista, costo_real / NULLIF(icp, 0) AS cpl_real
  FROM filas
  UNION ALL
  SELECT 'TOTAL', encontrados, unicos, icp, con_telefono, contactables, no_contactables_politica,
         costo_lista, costo_real, desperdicio_lista, desperdicio_real,
         costo_lista / NULLIF(icp, 0) AS cpl_lista, costo_real / NULLIF(icp, 0) AS cpl_real
  FROM total;

-- v_atribuciones (0006) no cambia.

-- El rol de runtime lee las vistas; los GRANT/REVOKE de la 0006 y la 0008 sobre las vistas que se reemplazan sobreviven.
GRANT SELECT ON public.v_costos, public.v_costo_evals, public.v_leads_icp, public.v_prorrateo,
  public.v_desperdicio, public.v_costo_por_lead, public.v_costo_por_canal, public.v_tablero_fuentes TO app_rt;

-- Roles de Supabase: el default privilege de `supabase_simulado.sql` le da ALL a anon/authenticated en cada objeto
-- nuevo de postgres, y estas vistas son nuevas. Sin este REVOKE, anon lee el libro de costos (principio III).
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON public.v_costos, public.v_costo_evals, public.v_leads_icp, public.v_prorrateo,
      public.v_desperdicio, public.v_costo_por_lead, public.v_costo_por_canal, public.v_tablero_fuentes
      FROM anon, authenticated;
  END IF;
END
$$;
