# Spec 001 — Walking skeleton

**Slice:** 001 · **Rama:** `feature/001-walking-skeleton` · **Tiempo:** sábado AM (≤ 3 h)
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
- `backend/tests/arquitectura/test_import_linter.py::test_detecta_import_prohibido` → un paquete canario con `import googlemaps` hace fallar `lint-imports` nombrando el contrato `forbidden`; `::test_repo_cumple_contratos` → el repo real pasa.
- `backend/tests/arquitectura/test_migraciones.py::test_upgrade_head_desde_vacio` → `alembic upgrade head` como `app_mig` sobre base vacía termina, la revisión actual coincide con `head` y `alembic check` no detecta drift.
- `backend/tests/arquitectura/test_secrets.py::test_app_no_arranca_con_url_de_migraciones` → con `MIGRATION_DATABASE_URL` en el entorno, la app falla al arrancar.
- `backend/tests/integration/test_rol_runtime.py::test_rol_runtime_no_es_super_ni_bypassrls_ni_puede_crear` → conectado como `app_rt`: `rolsuper` y `rolbypassrls` en false, y `CREATE TABLE` en `public` denegado.
- `frontend/src/App.test.tsx::muestra estado de la API` → con `/health` mockeado en ok, renderiza "API: ok".
- `frontend/e2e/health.spec.ts` → contra la URL pública de Railway, la página muestra "DB: ok".
- `.github/workflows/ci.yml` existe y es *required check* en `main` (verificado a mano una vez; luego el test de configuración del principio V).

## Fuera del alcance
Cualquier tabla de negocio, cualquier fuente, cualquier mensaje. Auth de usuarios (viene con el tenant en el slice 2). Tablero. Contrato `layers` de import-linter y suite de contrato por puerto (entran en el slice 2 con el primer módulo y el primer puerto; hoy nacerían verdes). Test de config de required checks, marca "src sin tests" y step "módulo sin doc" (diferidos, ver `plan.md` → Complexity Tracking).

## Decisiones técnicas
- **Back:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, `uv`. Estructura: `backend/app/{main.py,config.py,db.py,modelos.py,modulos/}`, `backend/tests/{unit,integration,arquitectura}`, `backend/evals/`. `seguridad/` nace con el cifrado.
- **Roles de DB desde el día 1:** `app_rt` (runtime) y `app_mig` (migraciones, dueño del schema `public`), los dos `NOSUPERUSER NOBYPASSRLS`. El `postgres` de Railway solo corre `backend/scripts/roles.sql` a mano (idempotente, sin passwords; se ponen con `\password`). El job `migrar` de CI usa `MIGRATION_DATABASE_URL` (`app_mig`, `sslmode=require`) desde el GitHub Environment `produccion`. `api` y `web` reciben solo `DATABASE_URL` con `app_rt`. `alembic/env.py` no importa la config de la app.
- **Front:** Vite + React + TypeScript, Vitest + Testing Library, Playwright. `VITE_API_URL` por entorno.
- **Railway:** proyecto con 3 servicios (`api`, `web`, `postgres`). `api` con Dockerfile; `web` separado: Dockerfile multi-stage (build con node, Caddy sirve `dist/`; ver `research.md` R5). Dominios públicos generados.
- **CI (`ci.yml`):** jobs `back` (uv sync, pytest, lint-imports, alembic desde cero + `alembic check` contra servicio Postgres), `front` (npm ci, vitest, build), `seguridad` (pip-audit, npm audit, gitleaks), `evals` (placeholder que pasa), `migrar` (solo push a `main`, environment `produccion`, después de los anteriores). Railway con "Wait for CI". `e2e.yml` solo con `workflow_dispatch`. CodeQL y Dependabot por configuración del repo (`.github/dependabot.yml`).
- **import-linter:** en este slice, contrato `forbidden` en `backend/pyproject.toml` contra `googlemaps`, `linkedin*`, `instaloader` y `facebook*`. Los contratos de capas (`dominio` no importa `aplicacion|infraestructura|fastapi|sqlalchemy|httpx`; `aplicacion` no importa `infraestructura|fastapi|sqlalchemy`) entran en el slice 2 con el primer módulo.
- **Secrets:** `.env.example` (ya existe; se suman `CORS_ORIGINS` y `E2E_BASE_URL`) con nombres, nunca valores. Variables de Railway: `DATABASE_URL`, `CORS_ORIGINS`, `CIFRADO_KEY`, `TYPESAFE_API_KEY`, `CROMA_API_KEY`, `SMTP_*` (cada una se agrega en su slice). `MIGRATION_DATABASE_URL` vive solo en el GitHub Environment `produccion`, nunca en Railway.

## Plan de tareas (TDD, en orden)
El detalle está en `plan.md` → "Orden de tareas". En resumen: 0 Railway primero (stub de `/health` con su test rojo) · 1 import-linter con canario · 2 guard de arranque · 3 roles + Alembic + `test_rol_runtime` · 4 `/health` real · 5 front · 6 higiene · 7 CI · 8 Railway completo + E2E · 9 protección de `main` + README + docs.

## Riesgos
- Railway tarda en el primer build de Docker: es la tarea 0, no la última.
- `app_rt` sin permisos sobre tablas nuevas: lo resuelven los `ALTER DEFAULT PRIVILEGES FOR ROLE app_mig` en `roles.sql`. El test que lo prueba entra en el slice 2, con la primera tabla.
- Las migraciones corren antes que el código nuevo: tienen que ser compatibles hacia atrás (expand/contract).
