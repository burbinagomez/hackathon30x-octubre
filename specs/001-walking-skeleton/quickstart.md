# Quickstart — validar el slice 001

## Prerrequisitos
`uv`, Node 22, Docker (solo para el Postgres local), `psql`, `railway` CLI, `gh`. Acceso al dashboard del proyecto Supabase del evento.

## Local
```bash
docker run -d --name pg001 -e POSTGRES_HOST_AUTH_METHOD=trust -p 5432:5432 postgres:16   # solo local: sin passwords
psql postgresql://postgres@localhost:5432/postgres -f backend/scripts/roles.sql
export TEST_DATABASE_URL=postgresql+psycopg://app_rt@localhost:5432/postgres
export TEST_ADMIN_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres  # solo tests: crea las bases vacías de test_migraciones
backend/scripts/migrar_local.sh postgresql://postgres@localhost:5432/postgres   # supabase/migrations en orden, como en CI

cd backend && uv sync && uv run pytest -q && uv run lint-imports
cd ../frontend && npm ci && npm test
```
**Esperado:** todo verde. `lint-imports` reporta el contrato `forbidden` como kept, con 0 broken.

## Producción (una vez, a mano)
En el dashboard de Supabase:
1. **Settings → API → Exposed schemas**: sacar `public`.
2. **Database → Extensions**: habilitar `pg_trgm` y `pgcrypto`.
3. **SQL editor**: pegar `backend/scripts/roles.sql` y correrlo. Sin passwords.

Passwords, desde `psql` (no quedan en ningún historial):
```bash
psql "postgresql://postgres.<ref>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
\password app_rt
```
Después hay que cargar:
- en el GitHub Environment `produccion`: secrets `SUPABASE_ACCESS_TOKEN` (Account → Access Tokens) y `SUPABASE_DB_PASSWORD` (la password de `postgres` del proyecto), variable `SUPABASE_PROJECT_REF`. Con eso el job `migrar` corre `supabase db push`;
- `DATABASE_URL` en el servicio `api` de Railway: `postgresql+psycopg://app_rt.<ref>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require` (modo transacción).

La password que pusiste con `\password app_rt` va después del usuario (`usuario:password@`) **solo en el valor de la variable de Railway**. No se escribe acá ni en ningún otro archivo.

El host exacto del pooler sale de **Connect** en el dashboard.

## Desplegado
```bash
curl -s https://api-production-92dc.up.railway.app/health        # {"status":"ok","db":"ok"}
gh workflow run e2e.yml -f base_url=https://web-production-ce4537.up.railway.app
```
**Esperado:** la página muestra `API: ok · DB: ok`.

## Barandales
- Setear en `api` cualquier `SUPABASE_*`, `MIGRATION_DATABASE_URL`, una key de Supabase o un access token del CLI (`sbp_…`) hace que el deploy falle al arrancar.
- `railway variables --service web` muestra solo `VITE_API_URL` (más las `RAILWAY_*` del sistema). Es manual: no hay token de Railway en CI.
- `curl https://<ref>.supabase.co/rest/v1/` con la publishable key no lista nada de `public`.
- `gh api repos/:owner/:repo/branches/main/protection` lista `back`, `front`, `seguridad`, `evals` e `imagenes` como required.
