# Data model — 001 Walking skeleton

Sin entidades de negocio (fuera del alcance). Solo esto:

| Objeto | Qué es | Reglas |
|---|---|---|
| `supabase_migrations.schema_migrations` | registro de migraciones del Supabase CLI (`version`, `name`) | lo escribe `db push` en prod y `migrar_local.sh` en CI y local; `0001_inicial.sql` no crea tablas |
| `app/modelos.py` | `metadata = MetaData()` vacío | sin importar `config`; es contra lo que compara el drift check |
| `postgres` (admin de Supabase) | no es SUPERUSER en Supabase; tiene `CREATEROLE` | corre `roles.sql` en el SQL editor, `\password` y las migraciones (`db push` desde el job `migrar`); nunca en runtime |
| `app_rt` | runtime de `api` | `LOGIN NOSUPERUSER NOBYPASSRLS`, no es dueño de nada ni puede hacer `CREATE` en `public`, `search_path = public, extensions`, `USAGE` sobre `extensions`; DML vía el `GRANT` de cada migración (tablas + secuencias); entra por el pooler en modo transacción |
| `anon`, `authenticated`, `service_role` | roles de Supabase | no se usan. `public` está fuera de la Data API; el `REVOKE` sobre `anon` y `authenticated` entra con la `0002` (slice 2) |
