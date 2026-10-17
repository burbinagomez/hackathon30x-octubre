# Implementation Plan: 001 — Walking skeleton

**Branch**: `feature/001-walking-skeleton` | **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)

## Summary

Back FastAPI con `GET /health` que consulta Postgres, front Vite+React que lo muestra, CI con tests y barandales (import-linter, migración desde cero, drift, auditorías, secrets) y deploy en Railway (2 servicios: `api`, `web`) con la base Postgres en Supabase (solo Postgres). Sin reglas de negocio. Las decisiones están en [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.12 (back, fijado con `uv python pin`), TypeScript 5 + Node 22 LTS (front)
**Primary Dependencies**: FastAPI, SQLAlchemy 2, psycopg 3, Alembic, pydantic-settings · React 18, Vite
**Storage**: Postgres en Supabase (solo Postgres), con `api` por Supavisor en modo transacción (6543) y migraciones por el pooler en modo sesión (5432). CI y local: `postgres:16`. Sin tablas de negocio; solo `alembic_version`.
**Testing**: pytest (+ TestClient), import-linter · Vitest + Testing Library · Playwright (solo `e2e/health.spec.ts`)
**Target Platform**: Railway (Linux, Docker) para `api` y `web`, Supabase para la base, GitHub Actions
**Project Type**: web app (backend + frontend)
**Performance Goals**: N/A en este slice
**Constraints**: ≤ 3 h; secrets solo en entorno; runtime (`app_rt`) y migraciones (`app_mig`) sin SUPERUSER ni BYPASSRLS
**Scale/Scope**: 1 endpoint, 1 página

## Constitution Check

*GATE: antes de Phase 0 y re-chequeado tras Phase 1.*

| Principio | Qué entrega este slice | Estado |
|---|---|---|
| I Hexagonal | Contrato `forbidden` en `backend/pyproject.toml` (`googlemaps`, `linkedin*`, `instaloader`, `facebook*`) con test canario que prueba que detecta la violación. Contrato `layers` y suite de contrato por puerto: slice 2, con el primer módulo y el primer puerto (ver Complexity). | ⚠️ |
| II Test primero | Cada tarea arranca con su test en rojo, incluida la tarea 0. CI corre back y front. Marca "src sin tests": diferida. | ⚠️ |
| III Tenant/RLS | `app_rt` y `app_mig` sin SUPERUSER ni BYPASSRLS. La app no arranca si ve `MIGRATION_DATABASE_URL`. `test_rol_runtime` prueba los atributos reales del rol en Postgres. Regla fijada: tenant por `SET LOCAL` dentro de la transacción (la impone el pooler en modo transacción). Tests RLS: N/A (no hay tablas con tenant). | ✅ |
| IV Migraciones | `0001_inicial` vacía; CI: Postgres vacío → `upgrade head` → `alembic check` contra `app/modelos.py`, acotado a `public` (`test_drift_mira_solo_public_aunque_cambie_search_path`). | ✅ |
| V Seguridad pipeline | `.env*` ignorado (ya está); pip-audit, npm audit (high), gitleaks en CI; CodeQL default setup; `dependabot.yml`; secret de migraciones en el GitHub Environment `produccion` limitado a `main`. La app no arranca con keys de Supabase en el entorno; `web` solo declara `ARG VITE_API_URL`. Required checks puestos a mano (el test de config queda diferido). | ⚠️ |
| VI Contacto cifrado | N/A: no hay columnas sensibles. | — |
| VII Cumplimiento | Solo la parte que aplica: import-linter prohíbe los clientes de las fuentes prohibidas. | ✅ |
| VIII Costos | N/A: no hay operaciones de salida. | — |
| IX Evals | Job `evals` placeholder que pasa. | ✅ |
| X Doc viva | README (cómo correr, variables, badge, atribuciones), `docs/arquitectura-backend.md` (incluye regla expand/contract), `docs/arquitectura-frontend.md`. Test de higiene: `CLAUDE.md` < 100 líneas. Step "módulo sin doc": diferido. | ⚠️ |

Los ⚠️ son desvíos justificados en Complexity Tracking. Re-chequeo post-diseño: sin violaciones nuevas.

## Project Structure

### Documentation (this feature)

```text
specs/001-walking-skeleton/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md
└── contracts/health.md
```

### Source Code

```text
.env.example                 # ya existe; se suman CORS_ORIGINS y E2E_BASE_URL
backend/
├── pyproject.toml           # deps + [tool.importlinter]
├── Dockerfile · .dockerignore   # multi-stage, ver research.md R-docker
├── uv.lock                  # --frozen lo exige
├── alembic.ini
├── alembic/{env.py, versions/0001_inicial.py}   # env.py: URL desde os.environ, sin importar config
├── scripts/roles.sql        # app_mig + app_rt, idempotente, sin passwords; se pega en el SQL editor de Supabase
├── app/{main.py, config.py, db.py, modelos.py}  # modelos.py: metadata = MetaData(), sin config; db.py: prepare_threshold=None
├── app/modulos/__init__.py  # vacío; los módulos llegan en slice 2
├── tests/unit/{test_health_stub.py, test_db.py} # test_health_stub: solo tarea 0b
├── tests/integration/{test_health.py, test_rol_runtime.py}
├── tests/arquitectura/{test_import_linter.py, test_migraciones.py, test_secrets.py, test_higiene.py}
└── evals/run.py             # placeholder
frontend/
├── package.json · vite.config.ts · Dockerfile · .dockerignore · Caddyfile
├── src/{main.tsx, App.tsx, App.test.tsx}
└── e2e/health.spec.ts · playwright.config.ts
.github/{workflows/ci.yml, workflows/e2e.yml, dependabot.yml}
.github/scripts/check_imagen.sh   # job `imagenes`: sin node/npm/uv/pip, no root, tope de MB
docs/{arquitectura-backend.md, arquitectura-frontend.md}
```

**Structure Decision**: web app con `backend/` y `frontend/` en la raíz, como fija la spec. Sin `seguridad/` todavía: nace cuando haya algo que cifrar (YAGNI).

## Orden de tareas (TDD)

0a. **Supabase** (a mano, sin código): proyecto nuevo para el evento. `public` sale de los esquemas expuestos de la Data API; se habilitan `pg_trgm` y `pgcrypto`. `roles.sql` se escribe en la tarea 3, pero se puede pegar en el SQL editor apenas exista. Se anota el `project-ref` y la región del pooler. **Verificar:** que el pooler acepta `app_rt.<ref>` y `app_mig.<ref>` (roles propios), y que el dueño de `public` quedó `app_mig` (`\dn+`).
0b. **Railway** (riesgo nº 1 de la spec). **Rojo:** `test_health_stub` (`GET /health` → 200). Después, `main.py` mínimo + Dockerfile. Se crea el proyecto Railway con 2 servicios (`api`, `web`) y el primer deploy de `api`, que construye mientras corren las tareas 1–6.
1. **Rojo:** `test_import_linter::test_detecta_import_prohibido`, un canario en `tmp_path` con `import googlemaps` que debe dar exit ≠ 0 nombrando el contrato. Después, el contrato `forbidden` → verde. Junto a `test_repo_cumple_contratos` (el repo real da exit 0).
2. **Rojo:** `test_secrets::test_app_no_arranca_con_secret_prohibido[…]` (levanta la app con TestClient y cada caso seteado → error que nombra la variable) y `test_dockerfile_web_solo_recibe_vite_api_url`. Después, el guard en `config.py`, instanciado al crear la app, y `ARG VITE_API_URL` como único `ARG` del Dockerfile de `web` → verde. `test_app_arranca_con_entorno_limpio` cuida que el guard no rechace todo.
3. `roles.sql` + `db.py` + Alembic (`env.py` desacoplado y fijado a `public`) + `modelos.py` + `0001_inicial`. **Rojo:** `test_upgrade_head_desde_vacio` (upgrade como `app_mig` + `alembic check`), `test_drift_mira_solo_public_aunque_cambie_search_path`, `test_rol_runtime` y `test_engine_desactiva_prepared_statements`. Después → verde.
4. **Rojo:** `test_health_consulta_db` (como `app_rt`: 200, `db == "ok"`) y `test_health_db_caida` (503). `/health` real → verde. `test_health_stub` se borra.
5. **Rojo:** `App.test.tsx`, ok y error. Después `App.tsx` → verde.
6. **Rojo:** `test_higiene` con un fixture de 101 líneas. Después → verde.
7. **Rojo:** `check_imagen.sh`, un caso por rama, verificando cada motivo en la salida (R-docker):
   - `python:3.12-slim` → `pip` y `root`;
   - `node:22-alpine` con `max_mb=250` → `node` y `npm`;
   - slim con `max_mb=1` → tamaño.

   Después, `ci.yml`:
   - `back`, `front`, `seguridad` y `evals`;
   - `imagenes`: construye las dos imágenes y les corre `check_imagen.sh`, con tope de 250 MB para `api` y 60 MB para `web` (R-docker);
   - `migrar`: solo en `main`, con environment `produccion` y `needs` de `back`, `front`, `seguridad` e `imagenes`.

   Más `dependabot.yml` (incluye `docker`) → push (con aviso previo) → CI verde.
8. Railway: variables (`DATABASE_URL` del pooler en modo transacción solo en `api`; `VITE_API_URL` solo en `web`), dominios, `CORS_ORIGINS`, "Wait for CI". `MIGRATION_DATABASE_URL` (pooler en modo sesión) en el Environment `produccion`. **Rojo:** `e2e/health.spec.ts` contra la URL pública, vía `workflow_dispatch` → verde.
9. Protección de `main` + required checks (`back`, `front`, `seguridad`, `evals`, `imagenes`) + README con badge + los dos docs de arquitectura.

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| Marca "PR toca src sin tests" (II), diferida | Con ≤3 h y sin `src` de negocio no hay nada que vigilar; entra en el slice 2 | Agregar ahora 1 step de CI que no vigila nada |
| Test de configuración de required checks (V), diferido | La spec lo pide a mano una vez; el test necesita un token de admin del repo en CI | Meter el token ahora: más superficie para un chequeo que se hace una sola vez |
| Step "módulo sin doc" (X), diferido | No hay módulos; nace con el primero (slice 2) | Un step que hoy siempre pasa |
| Contrato `layers` (I) y suite de contrato por puerto, al slice 2 | Sin módulos ni puertos, el test nacería verde y no probaría nada | Crear un módulo de relleno solo para que el contrato tenga algo que mirar |
| `test_secrets` prueba el arranque de la app, no las variables de Railway | Chequeo local y automático, sin token de Railway en CI; `test_rol_runtime` cubre el hueco de que alguien ponga la URL del owner en `DATABASE_URL` | `railway variables --json` en CI con `RAILWAY_TOKEN` |
| Migraciones en un job de CI, no en Railway | Railway no separa variables por fase: un pre-deploy en `api` dejaría `MIGRATION_DATABASE_URL` en el runtime (viola III) | Pre-deploy command en `api`; un 3.er servicio `migrate` (la spec fija 2) |
| CI prueba contra `postgres:16`, no contra Supabase | Un proyecto Supabase para CI es otra cuenta y otro secret; lo propio de Supabase lo cubren el unit test del engine, la emulación de roles del slice 2 y el E2E | Branching de Supabase o un segundo proyecto para CI |
