# Tasks: 001 — Walking skeleton

**Input:** `specs/001-walking-skeleton/` (plan.md, spec.md, research.md, data-model.md, contracts/health.md, quickstart.md)

**Tests:** obligatorios (constitución II y skill `slice-tdd`). Cada test se ve en ROJO, por la razón correcta, antes de implementar.

**Organización:** la spec tiene una sola historia, **US1**: "`/health` de punta a punta: back → DB → front → deploy". Las fases siguen el "Orden de tareas" del `plan.md` (0a…9). Los barandales (1–3) son la fase fundacional, porque toda la historia depende de ellos.

**Dueño:**
- 🧑B **burbinagomez** (base de datos y repo): cuentas de Supabase/GitHub, roles, secrets. Ninguno de estos valores pasa por mí ni queda en el repo.
- 🧑A **Angel** (Railway): proyecto y variables de Railway. Nada de base de datos.
- 🤖 **yo (Claude)**: el resto — código y tests, con un commit por tarea en `feature/001-walking-skeleton`. Sin push hasta mostrarte la lista de commits.

**Nota de arranque:** Environment de GitHub: `produccion`. Push por fase con OK. Nada de base de datos lo hace Angel.

## Formato: `[ID] [P?] [Story] Descripción`

---

## Fase 1: Setup (tareas 0a, 0b)

- [ ] T001 🧑B Verificar el proyecto Supabase del evento (ya existe). Anotar `project-ref` y región del pooler (no son secretos, pero no van al repo hasta el README de T033).
- [ ] T002 🧑B Supabase → **Settings → API → Exposed schemas**: sacar `public`. **Database → Extensions**: habilitar `pg_trgm` y `pgcrypto` (quedan en `extensions`).
- [ ] T003 🧑B Supabase: correr `\dn+ extensions` y `SELECT * FROM pg_default_acl` desde `psql` como `postgres` por el pooler en modo sesión. Pasarme **la salida** (no tiene secretos), que define si el `GRANT USAGE ON SCHEMA extensions` de `roles.sql` va a andar.
- [X] T004 🤖 Esqueleto del back: `backend/pyproject.toml` (`uv python pin 3.12`, sin patch; FastAPI, SQLAlchemy 2, `psycopg[binary]` 3, Alembic, pydantic-settings, uvicorn; dev: pytest, httpx, import-linter, pip-audit) + `backend/uv.lock` commiteado y `backend/app/__init__.py`, `backend/app/modulos/__init__.py` vacíos.
- [X] T005 🤖 **Rojo:** `backend/tests/unit/test_health_stub.py` (`GET /health` → 200). Verlo fallar por la ruta ausente, no por un import roto.
- [X] T006 🤖 **Verde:** `backend/app/main.py` mínimo con `/health` stub. Después, `backend/Dockerfile` multi-stage y `backend/.dockerignore` (R-docker):
  - builder `python:3.12-slim` (tag fijo) + `uv` copiado de `ghcr.io/astral-sh/uv:<tag>`, con `uv sync --frozen --no-dev --no-install-project`;
  - final con el mismo `WORKDIR /app`: copia solo `.venv` y `app/`, y corre `pip uninstall -y pip` antes de `USER`;
  - `USER app`;
  - `HEALTHCHECK` con `python -c urllib…` sobre `${PORT:-8000}`;
  - `CMD exec uvicorn … --port ${PORT:-8000}`.
- [ ] T007 🧑A Railway: crear el proyecto con 2 servicios (`api`, `web`) conectados al repo, `api` con root `backend/` y Dockerfile, y lanzar el primer deploy de `api` desde `feature/001-walking-skeleton`. Que construya mientras sigo con T008–T026.

## Fase 2: Fundacional — barandales (tareas 1–3)

**⚠️ Ningún trabajo de US1 empieza antes de que esta fase esté verde.**

### Tarea 1: import-linter
- [X] T008 🤖 **Rojo:** `backend/tests/arquitectura/test_import_linter.py::test_detecta_import_prohibido`. Un canario en `tmp_path` con `import googlemaps`, corrido con `lint-imports --config <tmp>`, debe dar exit ≠ 0 nombrando el contrato `forbidden`. Junto a `::test_repo_cumple_contratos` (el repo real da exit 0).
- [X] T009 🤖 **Verde:** contrato `forbidden` en `[tool.importlinter]` de `backend/pyproject.toml`, sobre `app`, contra `googlemaps`, `linkedin*`, `instaloader` y `facebook*`, con `include_external_packages = true`. Verificar contra la versión instalada que los wildcards andan; si no, nombres explícitos (R4).

### Tarea 2: guard de arranque y Dockerfile de `web`
- [X] T010 [P] 🤖 **Rojo:** `backend/tests/arquitectura/test_secrets.py`:
  - `::test_app_no_arranca_con_secret_prohibido[…]`, un caso por parámetro:
    - `MIGRATION_DATABASE_URL`;
    - un nombre `SUPABASE_*`;
    - un valor que empieza con `sb_publishable_` o `sb_secret_`;
    - un JWT con `role` en `{anon, service_role}`.

    En cada caso, el nombre de la variable aparece en `str(exc)`, y el valor no aparece en `str(exc)`, `caplog.text` ni `capsys`.
  - `::test_jwt_malformado_no_filtra_el_valor`: con `FOO_TOKEN` la app arranca; con `SUPABASE_X` rechaza. En los dos, el valor no aparece.
  - `::test_app_arranca_con_entorno_limpio`: con solo `DATABASE_URL` y `CORS_ORIGINS`, arranca.
- [X] T011 [P] 🤖 **Rojo:** `test_secrets.py::test_dockerfile_web_solo_recibe_vite_api_url`. Los `ARG` de `frontend/Dockerfile` son exactamente `{VITE_API_URL}`. Rojo porque el archivo no existe todavía.
- [X] T012 🤖 **Verde:** el guard en `backend/app/config.py` (pydantic-settings), instanciado al crear la app en `main.py`. El JWT se decodifica sin verificar firma y el error de decodificación se traga.
- [X] T013 🤖 **Verde:** `frontend/Dockerfile` multi-stage, `node:22-alpine` → `caddy:2-alpine` con tags fijos, `ARG VITE_API_URL` como único `ARG`, `USER` no root dueño de `/data` y `/config`, `setcap -r /usr/bin/caddy` en el build (con `libcap` instalado y borrado) y `HEALTHCHECK` con `wget`. Más `frontend/.dockerignore` y `frontend/Caddyfile` (R-docker):
  - `{ admin off }`;
  - sitio `:{$PORT:8080}`;
  - `handle /health { respond 200 }`;
  - `handle { root * /srv; try_files {path} /index.html; file_server }`.
- [X] T014 🤖 `.env.example`: sumar `CORS_ORIGINS=` y `E2E_BASE_URL=`, solo nombres.

### Tarea 3: roles, Alembic, drift y engine
- [ ] T015 🤖 `backend/scripts/roles.sql`, idempotente y sin passwords (R3):
  - `app_mig` y `app_rt` con `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB`, dentro de un `DO … IF NOT EXISTS`;
  - `GRANT app_mig TO CURRENT_USER`;
  - `ALTER SCHEMA public OWNER TO app_mig`;
  - `REVOKE CREATE ON SCHEMA public FROM PUBLIC`;
  - `GRANT USAGE ON SCHEMA public TO app_rt`;
  - `ALTER DEFAULT PRIVILEGES FOR ROLE app_mig`: tablas (SELECT, INSERT, UPDATE, DELETE) y secuencias (USAGE, SELECT) para `app_rt`;
  - `CREATE SCHEMA IF NOT EXISTS extensions` + `GRANT USAGE … TO app_rt, app_mig`;
  - `search_path = public, extensions` en los dos roles.
- [ ] T016 [P] 🤖 **Rojo:** `backend/tests/integration/test_rol_runtime.py::test_rol_runtime_no_es_super_ni_bypassrls_ni_puede_crear`. Como `app_rt`:
  - los 4 atributos (`rolsuper`, `rolbypassrls`, `rolcreaterole`, `rolcreatedb`) en false;
  - nada en `pg_namespace` ni en `pg_class` tiene dueño `app_rt`;
  - `CREATE TABLE` en `public` da permiso denegado;
  - `has_schema_privilege('app_rt','extensions','USAGE')` da true.

  Si falta `TEST_DATABASE_URL`, falla; no se salta.
- [ ] T017 [P] 🤖 **Rojo:** `backend/tests/arquitectura/test_migraciones.py`:
  - `::test_upgrade_head_desde_vacio`: `downgrade base` → `upgrade head` como `app_mig` → la revisión actual es `head` y `alembic check` da 0. `MIGRATION_DATABASE_URL` va solo en el `env=` del subproceso.
  - `::test_drift_mira_solo_public_aunque_cambie_search_path`: con `ajeno.t` creada y `PGOPTIONS="-c search_path=ajeno,public"`, `check` da 0 y `alembic_version` queda en `public`. Con una tabla extra en `public`, `check` da ≠ 0.
- [ ] T018 [P] 🤖 **Rojo:** `backend/tests/unit/test_db.py::test_engine_desactiva_prepared_statements`: el engine de `db.py` pasa `prepare_threshold=None`.
- [ ] T019 🤖 **Verde:**
  - `backend/app/modelos.py` con `metadata = MetaData()`, sin importar `config`;
  - `backend/app/db.py` con `connect_args={"prepare_threshold": None}`;
  - `backend/alembic.ini`;
  - `backend/alembic/env.py`: URL desde `os.environ["MIGRATION_DATABASE_URL"]`, sin importar `app.config`, `SET search_path TO public, extensions` al conectar, `target_metadata = metadata`, sin `version_table_schema`;
  - `backend/alembic/versions/0001_inicial.py` vacía.
- [ ] T020 🧑B Supabase (cuando T015 esté commiteado):
  - pegar `backend/scripts/roles.sql` en el **SQL editor** y correrlo;
  - poner las passwords con `\password app_mig` y `\password app_rt` desde `psql` (nunca en el SQL editor);
  - verificar con `\dn+ public` que el dueño es `app_mig`;
  - verificar que el pooler acepta `app_rt.<ref>` (6543) y `app_mig.<ref>` (5432) con `sslmode=require`.

  Pasarme solo las salidas, sin passwords. **Acá te aviso (0a/0b).**

## Fase 3: US1 — `/health` de punta a punta (tareas 4–5) 🎯 MVP

**Objetivo:** el back consulta la DB y el front muestra "API: ok · DB: ok".
**Prueba independiente:** `test_health_consulta_db` + `App.test.tsx` en verde, en local.

- [ ] T021 [P] [US1] 🤖 **Rojo:** `backend/tests/integration/test_health.py` contra `contracts/health.md`:
  - `::test_health_consulta_db`: como `app_rt`, 200 y `{"status":"ok","db":"ok"}`;
  - `::test_health_db_caida`: 503 y `{"status":"error","db":"error"}`, sin texto de la excepción en el body.
- [ ] T022 [US1] 🤖 **Verde:** `/health` real en `backend/app/main.py` (`SELECT 1` por `db.py`) + CORS solo para `CORS_ORIGINS`. Borrar `backend/tests/unit/test_health_stub.py`.
- [ ] T023 [P] [US1] 🤖 Esqueleto del front: `frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `src/main.tsx`; Vitest + Testing Library + MSW.
- [ ] T024 [US1] 🤖 **Rojo:** `frontend/src/App.test.tsx`:
  - `muestra estado de la API`: `/health` mockeado en ok → "API: ok · DB: ok";
  - con la llamada caída → "API: error";
  - con `db` distinto de ok → "DB: error".
- [ ] T025 [US1] 🤖 **Verde:** `frontend/src/App.tsx` llama `${VITE_API_URL}/health`.

## Fase 4: higiene, CI, deploy y cierre (tareas 6–9)

- [ ] T026 🤖 **Rojo:** `backend/tests/arquitectura/test_higiene.py`. Con un fixture de 101 líneas falla; el `CLAUDE.md` real (< 100 líneas) pasa. **Verde** después.
- [ ] T027 🤖 `backend/evals/run.py`, un placeholder que sale con 0.
- [ ] T028 🤖 **Rojo:** `.github/scripts/check_imagen.sh <imagen> <max_mb>`. Reporta cada motivo por nombre, y `pip` se busca también con `python -m pip --version`. Tiene que fallar, con el motivo en la salida, en tres casos:
  - `python:3.12-slim` pelada → `pip` y `root`;
  - `node:22-alpine` con `max_mb=250` → `node` y `npm`;
  - slim con `max_mb=1` → el tamaño.

  Después, contra las imágenes de T006 (250 MB) y T013 (60 MB) → verde.
- [ ] T029 🤖 `.github/workflows/ci.yml` con estos jobs (además, `imagenes`: build de las dos imágenes + `check_imagen.sh`):
  - `back`: `postgres:16` + `roles.sql` + passwords de test, `uv sync`, `pytest`, `lint-imports`, alembic desde cero + `check`;
  - `front`: `npm ci`, `vitest`, build;
  - `seguridad`: pip-audit, `npm audit --audit-level=high`, binario de gitleaks;
  - `evals`;
  - `migrar`: solo en push a `main`, con `environment: produccion` y `needs` de `back`, `front`, `seguridad` e `imagenes`.

  Más `.github/workflows/e2e.yml` (`workflow_dispatch`, input `base_url` → `E2E_BASE_URL`) y `.github/dependabot.yml` (pip/uv, npm, github-actions y docker).
- [ ] T030 🧑B GitHub: crear el Environment `produccion`, limitado a `main`, con el secret `MIGRATION_DATABASE_URL` (pooler en modo sesión, `app_mig.<ref>`). Activar CodeQL default setup.
- [ ] T031 🧑A Railway:
  - `api`: `DATABASE_URL` (pooler en modo transacción, `app_rt.<ref>`, 6543) y `CORS_ORIGINS` (dominio de `web`);
  - `web`: solo `VITE_API_URL`;
  - dominios públicos generados;
  - "Wait for CI" activado en los dos servicios;
  - `web` con root `frontend/`.
- [ ] T032 [US1] 🤖 **Rojo:** `frontend/e2e/health.spec.ts` + `frontend/playwright.config.ts`. Contra la URL pública, la página muestra "DB: ok". Lo corrés con `gh workflow run e2e.yml -f base_url=…` después del deploy, y ahí pasa a verde.
- [ ] T033 🤖 `README.md`: cómo correr, variables (nombres), badge de CI, riesgo del pooler expuesto, atribuciones. Más `docs/arquitectura-backend.md` (incluye expand/contract y `SET LOCAL`) y `docs/arquitectura-frontend.md`.
- [ ] T034 🧑B Protección de `main`: required checks `back`, `front`, `seguridad`, `evals` e `imagenes`, más 1 aprobación. Verificar con `gh api repos/:owner/:repo/branches/main/protection`.

## Dependencias

- T001–T003 (Supabase) y T004–T006 (stub) van en paralelo. T007 necesita T006 en la rama remota, así que es **el primer push** (te aviso antes).
- Fase 2 depende de T004. T020 depende de T015 y de T001–T002.
- US1 depende de toda la Fase 2. T021–T022 necesitan Postgres local (quickstart); no necesitan Supabase.
- T029 depende de T026–T028. T030–T031 dependen de T020. T032 depende de T029–T031 y de un deploy verde.
- T034 va al final: los checks tienen que existir (haber corrido una vez) para poder marcarlos como required.

## Paralelo

- Mientras vos hacés T001–T003 y T007, yo hago T004–T019.
- Dentro de la tarea 2, T010 y T011 son archivos distintos. Dentro de la tarea 3, T016, T017 y T018 también. T021 y T023 son back y front.

## Estrategia

MVP = Fases 1–3 en local (`/health` real + front, con todos los barandales). La Fase 4 lo pone en CI y en Railway. Si el tiempo (≤ 3 h) no alcanza, se corta en el último verde (skill `slice-tdd`), y lo primero en caer es T033 (docs), no los barandales.
