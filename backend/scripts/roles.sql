-- Rol de runtime (R3). Idempotente y SIN password: se pone aparte con \password (Supabase)
-- o ALTER ROLE ... PASSWORD con un valor de test (CI). En Supabase se pega en el SQL editor.
-- Las migraciones corren como postgres (`supabase db push`): no hay rol de migraciones propio.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rt') THEN
    CREATE ROLE app_rt LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
  END IF;
END
$$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_rt;

-- Supabase instala las extensiones acá; en vanilla lo crea este script.
CREATE SCHEMA IF NOT EXISTS extensions;
GRANT USAGE ON SCHEMA extensions TO app_rt;

ALTER ROLE app_rt SET search_path = public, extensions;
