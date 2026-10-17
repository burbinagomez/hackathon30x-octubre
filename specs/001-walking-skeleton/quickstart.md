# Quickstart — validar el slice 001

## Prerrequisitos
`uv`, Node 22, Docker (solo para el Postgres local), `psql`, `railway` CLI, `gh`. Acceso al dashboard del proyecto Supabase del evento.

## Local
```bash
docker run -d --name pg001 -e POSTGRES_HOST_AUTH_METHOD=trust -p 5432:5432 postgres:16   # solo local: sin passwords
psql postgresql://postgres@localhost:5432/postgres -f backend/scripts/roles.sql
export TEST_DATABASE_URL=postgresql+psycopg://app_rt@localhost:5432/postgres
export TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://app_mig@localhost:5432/postgres

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
\password app_mig
\password app_rt
\dn+ public                          # dueño: app_mig
```
Después hay que cargar:
- `MIGRATION_DATABASE_URL` en el GitHub Environment `produccion`: `postgresql+psycopg://app_mig.<ref>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require` (modo sesión);
- `DATABASE_URL` en el servicio `api` de Railway: `postgresql+psycopg://app_rt.<ref>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require` (modo transacción).

La password que pusiste con `\password` va después del usuario (`usuario:password@`) **solo en el valor del secret**. No se escribe acá ni en ningún otro archivo.

El host exacto del pooler sale de **Connect** en el dashboard.

## Desplegado
```bash
curl -s https://<api>.up.railway.app/health        # {"status":"ok","db":"ok"}
gh workflow run e2e.yml -f base_url=https://<web>.up.railway.app
```
**Esperado:** la página muestra `API: ok · DB: ok`.

## Barandales
- Setear `MIGRATION_DATABASE_URL` o cualquier key de Supabase en `api` hace que el deploy falle al arrancar.
- `railway variables --service web` muestra solo `VITE_API_URL` (más las `RAILWAY_*` del sistema). Es manual: no hay token de Railway en CI.
- `curl https://<ref>.supabase.co/rest/v1/` con la publishable key no lista nada de `public`.
- `gh api repos/:owner/:repo/branches/main/protection` lista `back`, `front`, `seguridad` y `evals` como required.
