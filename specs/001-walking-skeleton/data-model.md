# Data model — 001 Walking skeleton

Sin entidades de negocio (fuera del alcance). Solo esto:

| Objeto | Qué es | Reglas |
|---|---|---|
| `alembic_version` | tabla de Alembic | `0001_inicial` es `head` y está vacía |
| `app/modelos.py` | `metadata = MetaData()` vacío | sin importar `config`; es el `target_metadata` de Alembic |
| `postgres` (admin de Supabase) | no es SUPERUSER en Supabase; tiene `CREATEROLE` | solo corre `roles.sql` en el SQL editor y `\password`; nunca en CI ni en runtime |
| `app_mig` | migraciones | `LOGIN NOSUPERUSER NOBYPASSRLS`, dueño del schema `public`, `search_path = public, extensions`, `USAGE` sobre `extensions`; su URL (pooler en modo sesión) vive solo en el Environment `produccion` (job `migrar`) |
| `app_rt` | runtime de `api` | `LOGIN NOSUPERUSER NOBYPASSRLS`, no es dueño de nada ni puede hacer `CREATE` en `public`, `search_path = public, extensions`, `USAGE` sobre `extensions`; DML vía `DEFAULT PRIVILEGES FOR ROLE app_mig` (tablas + secuencias); entra por el pooler en modo transacción |
| `anon`, `authenticated`, `service_role` | roles de Supabase | no se usan. `public` está fuera de la Data API; el `REVOKE` sobre `anon` y `authenticated` entra con la `0002` (slice 2) |
