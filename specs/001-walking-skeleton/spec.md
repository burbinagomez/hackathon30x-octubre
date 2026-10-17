# Spec 001 — Walking skeleton

**Slice:** 001 · **Rama:** `slice/001-walking-skeleton` · **Tiempo:** sábado AM (≤ 3 h)
**Depende de:** nada. **Desbloquea:** todos los demás.

## Para quién
El equipo. Nadie externo ve este slice; su valor es que **todo lo que venga después se despliega solo y se prueba solo**.

## Qué hace
Un repo con back, front y base de datos **desplegados en Railway, públicos, en verde en CI, con secrets fuera del repo y con el barandal de arquitectura puesto**, antes de escribir una sola regla de negocio.

## Flujo principal
1. `GET /health` en el back responde `200 {"status":"ok","db":"ok"}` tras consultar la base.
2. El front carga una página que llama a `/health` y muestra "API: ok · DB: ok".
3. Un push a `main` corre CI (tests back + front + import-linter + migración desde cero + auditorías) y, si pasa, Railway redespliega los tres servicios.

## Terminado cuando (tests que hoy fallan)
- `backend/tests/integration/test_health.py::test_health_consulta_db` → 200 y `db == "ok"` contra Postgres de prueba.
- `backend/tests/arquitectura/test_import_linter.py` → `lint-imports` pasa con los contratos de capas declarados (aunque los módulos estén vacíos).
- `backend/tests/arquitectura/test_migraciones.py::test_upgrade_head_desde_vacio` → `alembic upgrade head` sobre base vacía termina y la revisión actual coincide con `head`.
- `backend/tests/arquitectura/test_secrets.py::test_runtime_no_tiene_url_de_migraciones` → las variables del servicio `api` no incluyen `MIGRATION_DATABASE_URL`.
- `frontend/src/App.test.tsx::muestra estado de la API` → con `/health` mockeado en ok, renderiza "API: ok".
- `frontend/e2e/health.spec.ts` → contra la URL pública de Railway, la página muestra "DB: ok".
- `.github/workflows/ci.yml` existe y es *required check* en `main` (verificado a mano una vez; luego el test de configuración del principio V).

## Fuera del alcance
Cualquier tabla de negocio, cualquier fuente, cualquier mensaje. Auth de usuarios (viene con el tenant en el slice 2). Tablero.

## Decisiones técnicas
- **Back:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, `uv`. Estructura: `backend/app/{main.py,config.py,db.py,modulos/,seguridad/}`, `backend/tests/{unit,integration,arquitectura}`, `backend/evals/`.
- **Roles de DB desde el día 1:** `app_rt` (runtime, sin owner, sin BYPASSRLS) y `app_mig` (migraciones). Railway Postgres crea el owner; el job de migraciones usa `MIGRATION_DATABASE_URL`; `api`/`web` solo `DATABASE_URL` con `app_rt`. Script `backend/scripts/roles.sql` crea `app_rt`.
- **Front:** Vite + React + TypeScript, Vitest + Testing Library, Playwright. `VITE_API_URL` por entorno.
- **Railway:** proyecto con 3 servicios (`api`, `web`, `postgres`). `api` con Dockerfile; `web` build estático servido por el mismo servicio o por `web` separado (decidir en plan). Dominios públicos generados.
- **CI (`ci.yml`):** jobs `back` (uv sync, pytest, lint-imports, alembic desde cero contra servicio Postgres), `front` (npm ci, vitest, build), `seguridad` (pip-audit, npm audit, gitleaks o equivalente), `evals` (vacío por ahora, placeholder que pasa). CodeQL y Dependabot por configuración del repo (`.github/dependabot.yml`).
- **import-linter:** contratos iniciales en `backend/pyproject.toml`: `dominio` no importa `aplicacion|infraestructura|fastapi|sqlalchemy|httpx`; `aplicacion` no importa `infraestructura|fastapi|sqlalchemy`. Lista de módulos prohibidos: `googlemaps`, `linkedin*`, `instaloader`, `facebook*`.
- **Secrets:** `.env.example` con nombres, nunca valores. Railway variables: `DATABASE_URL`, `MIGRATION_DATABASE_URL` (solo job), `CIFRADO_KEY`, `TYPESAFE_API_KEY`, `CROMA_API_KEY`, `SMTP_*` (se agregan en su slice).

## Plan de tareas (TDD, en orden)
1. Esqueleto de carpetas + `pyproject` + contratos de import-linter → test de arquitectura rojo → verde.
2. `config.py` + `db.py` + migración `0001_inicial` (vacía) → test de migración desde vacío rojo → verde.
3. `GET /health` → test de integración rojo → verde.
4. Front con `App.tsx` que consulta `/health` → test Vitest rojo → verde.
5. `ci.yml` + `dependabot.yml` → push → CI verde.
6. Railway: crear proyecto, 3 servicios, variables, dominios → `e2e/health.spec.ts` contra URL pública → verde.
7. Rama protegida en `main` con los checks como required. README con el badge.

## Riesgos
- Railway tarda en el primer build de Docker: empezar por aquí, no al final.
- `app_rt` sin permisos sobre tablas nuevas: la migración debe hacer `GRANT` explícito (plantilla en `alembic/plantilla_grant.py`).
