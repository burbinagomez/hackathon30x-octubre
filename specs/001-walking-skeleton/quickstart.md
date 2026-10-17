# Quickstart — validar el slice 001

## Prerrequisitos
`uv`, Node 22, Docker (solo para el Postgres local), `railway` CLI, `gh`.

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
```bash
railway connect postgres            # psql como postgres
\i backend/scripts/roles.sql
\password app_mig
\password app_rt
```
Después hay que cargar `MIGRATION_DATABASE_URL` (`app_mig`, `?sslmode=require`) en el GitHub Environment `produccion`, y `DATABASE_URL` (`app_rt`) en el servicio `api` de Railway.

## Desplegado
```bash
curl -s https://<api>.up.railway.app/health        # {"status":"ok","db":"ok"}
gh workflow run e2e.yml -f base_url=https://<web>.up.railway.app
```
**Esperado:** la página muestra `API: ok · DB: ok`.

## Barandales
- Setear `MIGRATION_DATABASE_URL` en `api` hace que el deploy falle al arrancar.
- `gh api repos/:owner/:repo/branches/main/protection` lista `back`, `front`, `seguridad` y `evals` como required.
