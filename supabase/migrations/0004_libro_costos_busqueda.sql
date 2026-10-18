-- ESQUELETO T005 [MIN] (sin usuarios: pausado por el dueño). Se reemplaza por el DDL aprobado al final.
CREATE VIEW public.v_tablero_fuentes AS
  SELECT ''::text AS fuente, 0::bigint AS encontrados, 0::bigint AS unicos WHERE false;

CREATE VIEW public.v_atribuciones AS
  SELECT ''::text AS fuente, ''::text AS texto, ''::text AS url, 0 AS orden WHERE false;
GRANT SELECT ON public.v_tablero_fuentes, public.v_atribuciones TO app_rt;
