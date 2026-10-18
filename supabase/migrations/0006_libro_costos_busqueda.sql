-- 0004: libro de costos y búsqueda [MIN]. SQL a mano. Corre como postgres (dueño). Va después de la 0003.
-- Login con Supabase Auth (decisión del dueño, 2026-10-18): usuarios no guarda email ni clave; el email vive en auth.users.

-- P1 (dueño, 2026-10-18): unión de los 8 estados. Un solo ALTER: nunca queda la tabla sin CHECK.
ALTER TABLE public.busquedas
  DROP CONSTRAINT busquedas_estado_check,
  ADD CONSTRAINT busquedas_estado_check CHECK (estado IN (
    'creada', 'terminada', 'con_errores',
    'borrador', 'ejecutando', 'completada', 'tope_alcanzado', 'error'));

-- auth_user_id = auth.users.id = claim `sub` del access token de Supabase. Sin email ni clave: viven en auth.users.
-- Sin FK a auth.users: en CI y local (postgres vanilla) el esquema auth no existe, y una FK condicional haría que
-- prod y CI tengan esquemas distintos que el drift check no ve. La autoridad es esta fila: si no hay fila, no hay acceso.
CREATE TABLE public.usuarios (
  auth_user_id uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES public.tenants(id),
  idioma       text CHECK (idioma IN ('es', 'en')),
  creado_en    timestamptz NOT NULL DEFAULT now()
);

-- RLS sin FORCE a propósito: app_rt no es dueño y la política lo alcanza; el dueño (postgres) es quien
-- corre tenant_de_usuario antes de conocer el tenant. Con FORCE, esa función fallaría o dependería de BYPASSRLS.
-- app_rt no tiene ningún privilegio sobre la tabla: entra solo por la función.
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_aislado ON public.usuarios
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

-- Resolver el tenant: después de verificar el token, antes de conocer el tenant. Devuelve la fila de ESE
-- auth_user_id y nada más (PRIMARY KEY: 0 o 1 fila). El tenant NO sale del token (user_metadata lo edita el usuario).
-- Todo calificado con public.; pg_catalog va implícito primero, pg_temp al final.
CREATE FUNCTION public.tenant_de_usuario(p_auth_user_id uuid)
  RETURNS TABLE (tenant_id uuid, idioma_usuario text, idioma_tenant text)
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
  SELECT u.tenant_id, u.idioma, t.idioma
  FROM public.usuarios u
  JOIN public.tenants t ON t.id = u.tenant_id
  WHERE u.auth_user_id = p_auth_user_id
$$;
REVOKE ALL ON FUNCTION public.tenant_de_usuario(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.tenant_de_usuario(uuid) TO app_rt;

-- Vistas [MIN]. security_invoker: corren como app_rt y pasan por la RLS de lead_fuentes.
-- Pulido: un CREATE OR REPLACE VIEW sin WITH (security_invoker = true) BORRA la opción; repetirla siempre.
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

-- El EXECUTE a PUBLIC de las funciones nuevas es un default GLOBAL de Postgres: un ALTER DEFAULT PRIVILEGES
-- ... IN SCHEMA no lo puede sacar, y anon/authenticated lo heredan por PUBLIC. Se cierra para todo lo que cree postgres.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- Roles de Supabase. Supabase da EXECUTE en funciones nuevas de public a anon/authenticated por default
-- privileges; la 0002 solo cerró TABLES y SEQUENCES. Solo si existen (en vanilla no hay nada que revocar).
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON FUNCTION public.tenant_de_usuario(uuid) FROM anon, authenticated;
    REVOKE ALL ON public.usuarios, public.v_tablero_fuentes, public.v_atribuciones FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
  END IF;
END
$$;
