-- ESQUELETO T005/T008 [MIN] (sin usuarios: pausado). Se reemplaza por el DDL aprobado al final.
ALTER TABLE public.busquedas
  DROP CONSTRAINT busquedas_estado_check,
  ADD CONSTRAINT busquedas_estado_check CHECK (estado IN (
    'creada', 'terminada', 'con_errores',
    'borrador', 'ejecutando', 'completada', 'tope_alcanzado', 'error'));

CREATE VIEW public.v_tablero_fuentes WITH (security_invoker = true) AS
  SELECT fuente, count(*) AS encontrados, count(DISTINCT lead_id) AS unicos
  FROM public.lead_fuentes
  GROUP BY fuente
  UNION ALL
  SELECT 'TOTAL', count(*), count(DISTINCT lead_id)
  FROM public.lead_fuentes
  HAVING count(*) > 0;

CREATE VIEW public.v_atribuciones WITH (security_invoker = true) AS
  SELECT a.fuente, a.texto, a.url, a.orden
  FROM (VALUES
    ('osm_overpass', '© OpenStreetMap contributors', 'https://www.openstreetmap.org/copyright', 1),
    ('datos_gov_co_rues', 'Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)',
     'https://creativecommons.org/licenses/by-sa/4.0/', 2)
  ) AS a(fuente, texto, url, orden)
  WHERE EXISTS (SELECT 1 FROM public.lead_fuentes lf WHERE lf.fuente = a.fuente);

GRANT SELECT ON public.v_tablero_fuentes, public.v_atribuciones TO app_rt;
