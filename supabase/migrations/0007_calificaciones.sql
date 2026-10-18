-- 008: calificaciones de Dapta y CPQL por fuente. SQL a mano. Corre como postgres (dueño).
-- El número es el siguiente libre en main: si al mergear ya entró otra 0007, se renombra a la siguiente.
CREATE TABLE public.calificaciones (
  tenant_id     uuid NOT NULL REFERENCES public.tenants(id),
  lead_id       uuid NOT NULL,
  calificado    boolean NOT NULL,
  calificado_en timestamptz NOT NULL,
  minutos       numeric NOT NULL CHECK (minutos BETWEEN 0 AND 60),
  importado_en  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, lead_id),
  -- Compuesta: una FK no pasa por RLS (igual que la 0002).
  FOREIGN KEY (tenant_id, lead_id) REFERENCES public.leads (tenant_id, id)
);

-- Sin UPDATE ni DELETE: un resultado distinto para un lead ya importado es un conflicto que resuelve un humano.
GRANT SELECT, INSERT ON public.calificaciones TO app_rt;

ALTER TABLE public.calificaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_aislado ON public.calificaciones
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

-- CPQL por fuente = costo de la fuente / leads calificados de la fuente. Divisor 0 o sin costos: NULL ("sin dato").
-- Igual que el tablero: los costos de evals no entran. El dapta_llamada no tiene fuente: entra solo en TOTAL.
-- security_invoker: corre como app_rt y pasa por la RLS de costos, lead_fuentes y calificaciones.
-- Un CREATE OR REPLACE VIEW sin WITH (security_invoker = true) BORRA la opción; repetirla siempre.
CREATE VIEW public.v_cpql WITH (security_invoker = true) AS
  WITH costo AS (
    SELECT fuente,
           sum(unidades * costo_unitario) AS costo_lista,
           sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END) AS costo_real
    FROM public.costos
    WHERE fuente IS NOT NULL AND fuente <> 'evals'
    GROUP BY fuente
  ), calif AS (
    SELECT lf.fuente, count(DISTINCT lf.lead_id) AS calificados
    FROM public.lead_fuentes lf
    JOIN public.calificaciones c ON c.tenant_id = lf.tenant_id AND c.lead_id = lf.lead_id
    WHERE c.calificado
    GROUP BY lf.fuente
  ), fuentes AS (
    SELECT fuente FROM costo UNION SELECT fuente FROM public.lead_fuentes
  )
  SELECT f.fuente, co.costo_lista, co.costo_real, coalesce(ca.calificados, 0) AS calificados,
         co.costo_lista / NULLIF(ca.calificados, 0) AS cpql_lista,
         co.costo_real  / NULLIF(ca.calificados, 0) AS cpql_real
  FROM fuentes f
  LEFT JOIN costo co USING (fuente)
  LEFT JOIN calif ca USING (fuente)
  UNION ALL
  SELECT 'TOTAL', t.costo_lista, t.costo_real, t.calificados,
         t.costo_lista / NULLIF(t.calificados, 0), t.costo_real / NULLIF(t.calificados, 0)
  FROM (
    SELECT (SELECT sum(unidades * costo_unitario) FROM public.costos WHERE fuente IS DISTINCT FROM 'evals') AS costo_lista,
           (SELECT sum(CASE WHEN gratis THEN 0 ELSE unidades * costo_unitario END) FROM public.costos
             WHERE fuente IS DISTINCT FROM 'evals') AS costo_real,
           (SELECT count(*) FROM public.calificaciones WHERE calificado) AS calificados
  ) t
  -- Como el HAVING de v_tablero_fuentes: sin datos del tenant no hay fila TOTAL.
  WHERE t.costo_lista IS NOT NULL OR EXISTS (SELECT 1 FROM public.lead_fuentes);

GRANT SELECT ON public.v_cpql TO app_rt;

-- Roles de Supabase: sin acceso. Solo si existen (en vanilla no hay nada que revocar), como en la 0006.
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON public.calificaciones, public.v_cpql FROM anon, authenticated;
  END IF;
END
$$;
