-- Roles de la app (R3). Idempotente y SIN passwords: se ponen aparte con \password (Supabase)
-- o ALTER ROLE ... PASSWORD con valores de test (CI). En Supabase se pega en el SQL editor.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_mig') THEN
    CREATE ROLE app_mig LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rt') THEN
    CREATE ROLE app_rt LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
  END IF;
END
$$;

-- En Supabase postgres no es superusuario: para cambiar el dueño tiene que poder SET ROLE app_mig.
GRANT app_mig TO CURRENT_USER;

ALTER SCHEMA public OWNER TO app_mig;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_rt;

-- FOR ROLE app_mig: aplica a lo que crean las migraciones, no a quien corre este script.
ALTER DEFAULT PRIVILEGES FOR ROLE app_mig IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rt;
ALTER DEFAULT PRIVILEGES FOR ROLE app_mig IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_rt;

-- Supabase instala las extensiones acá; en vanilla lo crea este script.
CREATE SCHEMA IF NOT EXISTS extensions;
GRANT USAGE ON SCHEMA extensions TO app_rt, app_mig;

ALTER ROLE app_mig SET search_path = public, extensions;
ALTER ROLE app_rt SET search_path = public, extensions;
