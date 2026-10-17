# Spec 001 — Walking skeleton

**Slice:** 001 · **Rama:** `feature/001-walking-skeleton` · **Tiempo:** sábado AM (≤ 3 h)
**Depende de:** nada. **Desbloquea:** todos los demás.

## Para quién
El equipo. Nadie externo ve este slice; su valor es que **todo lo que venga después se despliega solo y se prueba solo**.

## Qué hace
Un repo con back y front **desplegados en Railway** y la base **Postgres en Supabase** (solo Postgres: sin Auth, Storage, Edge Functions ni Data API sobre `public`), **públicos, en verde en CI, con secrets fuera del repo y con el barandal de arquitectura puesto**, antes de escribir una sola regla de negocio.

## Flujo principal
1. `GET /health` en el back responde `200 {"status":"ok","db":"ok"}` tras consultar la base.
2. El front carga una página que llama a `/health` y muestra "API: ok · DB: ok".
3. Un push a `main` corre CI (tests back + front + import-linter + migración desde cero + auditorías), migra Supabase desde el job `migrar` y, si todo pasa, Railway redespliega `api` y `web`.

## Terminado cuando (tests que hoy fallan)
- `backend/tests/integration/test_health.py::test_health_consulta_db` → 200 y `db == "ok"` contra Postgres de prueba.
- `backend/tests/arquitectura/test_import_linter.py::test_detecta_import_prohibido` → un paquete canario con `import googlemaps` hace fallar `lint-imports` nombrando el contrato `forbidden`; `::test_repo_cumple_contratos` → el repo real pasa.
- `backend/tests/arquitectura/test_migraciones.py::test_migrar_local_desde_vacio_dos_veces_sin_drift` → `scripts/migrar_local.sh` aplica `supabase/migrations/*.sql` sobre una base nueva, la segunda corrida también termina en 0 y `compare_metadata` contra `app/modelos.py` no detecta drift.
- `::test_migracion_aplicada_no_se_reaplica` → una migración ya registrada en `supabase_migrations.schema_migrations` no se vuelve a aplicar.
- `::test_migracion_rota_falla_claro_y_no_deja_nada` → una migración que falla corta con exit ≠ 0, el error nombra el archivo y no queda nada a medias.
- `::test_drift_mira_solo_public_aunque_cambie_search_path` → con una tabla `ajeno.t` que no está en los modelos y la conexión con `-c search_path=ajeno,public`, el drift da vacío. Con una tabla extra en `public`, no.
- `backend/tests/arquitectura/test_secrets.py::test_app_no_arranca_con_secret_prohibido[…]` → la app falla al arrancar si el entorno trae cualquiera de estos casos (uno por parámetro):
  - `MIGRATION_DATABASE_URL`;
  - una variable cuyo nombre empieza con `SUPABASE_` (`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`…);
  - un valor que empieza con `sb_publishable_` o `sb_secret_` (keys nuevas de Supabase) o `sbp_` (access token del CLI), con cualquier nombre de variable;
  - un JWT cuyo payload trae `"role"` igual a `anon` o `service_role` (keys legacy), con cualquier nombre de variable.
  
  En cada caso, el nombre de la variable aparece en `str(exc)`, y el valor no aparece en `str(exc)` ni en `caplog.text`/`capsys`.
  `::test_jwt_malformado_no_filtra_el_valor` → un valor con forma de JWT pero payload que no decodifica: el guard se traga el error de decodificación. Parametrizado: con nombre neutro (`FOO_TOKEN`) la app arranca; con `SUPABASE_X` y el mismo valor, rechaza y el nombre aparece en `str(exc)`. En los dos, el valor no aparece en `str(exc)` ni en `caplog.text`/`capsys`.
  `::test_app_arranca_con_entorno_limpio` → con solo `DATABASE_URL` y `CORS_ORIGINS`, arranca.
- `backend/tests/arquitectura/test_secrets.py::test_dockerfile_web_solo_recibe_vite_api_url` → los `ARG` de `frontend/Dockerfile` son exactamente `{VITE_API_URL}`. Es lo único de las variables de Railway que puede llegar al bundle de `web`.
- `backend/tests/unit/test_db.py::test_engine_desactiva_prepared_statements` → el engine que arma `db.py` pasa `prepare_threshold=None` a psycopg, porque Supavisor en modo transacción no soporta prepared statements.
- `backend/tests/integration/test_rol_runtime.py::test_rol_runtime_no_es_super_ni_bypassrls_ni_puede_crear` → conectado como `app_rt`: `rolsuper`, `rolbypassrls`, `rolcreaterole` y `rolcreatedb` en false; ningún objeto de `pg_namespace` ni de `pg_class` tiene a `app_rt` como dueño; `CREATE TABLE` en `public` denegado; y `has_schema_privilege('app_rt','extensions','USAGE')` en true.
- `frontend/src/App.test.tsx::muestra estado de la API` → con `/health` mockeado en ok, renderiza "API: ok".
- `frontend/e2e/health.spec.ts` → contra la URL pública de Railway, la página muestra "DB: ok".
- Job `imagenes` de `ci.yml` → construye `api` y `web` y falla si la imagen final tiene `node`/`npm`/`uv`/`pip`, si corre como root, o si pesa más de 250 MB (`api`) / 60 MB (`web`), nombrando cada motivo. Rojo: `check_imagen.sh` falla y nombra el motivo en tres casos:
  - `python:3.12-slim` pelada → `pip` y `root`;
  - `node:22-alpine` con `max_mb=250` → `node` y `npm`;
  - slim con `max_mb=1` → el tamaño.
- `.github/workflows/ci.yml` existe y es *required check* en `main` (verificado a mano una vez; luego el test de configuración del principio V).

## Fuera del alcance
Cualquier tabla de negocio, cualquier fuente, cualquier mensaje. Auth de usuarios (viene con el tenant en el slice 2). Tablero. Contrato `layers` de import-linter y suite de contrato por puerto (entran en el slice 2 con el primer módulo y el primer puerto; hoy nacerían verdes). Test de config de required checks, marca "src sin tests" y step "módulo sin doc" (diferidos, ver `plan.md` → Complexity Tracking).

## Decisiones técnicas
- **Back:** Python 3.12, FastAPI, SQLAlchemy 2, `uv`. Esquema en `supabase/migrations/NNNN_nombre.sql`, SQL a mano. Estructura: `backend/app/{main.py,config.py,db.py,modelos.py,modulos/}`, `backend/tests/{unit,integration,arquitectura}`, `backend/evals/`. `seguridad/` nace con el cifrado.
- **Supabase, solo Postgres:** proyecto nuevo para el evento. En **Settings → API**, `public` sale de los esquemas expuestos por la Data API. `pg_trgm` y `pgcrypto` se habilitan desde el dashboard (quedan en el esquema `extensions`). El back no usa ningún SDK ni key de Supabase: habla Postgres y nada más.
- **Roles de DB desde el día 1:** solo `app_rt` (runtime: `LOGIN NOSUPERUSER NOBYPASSRLS`, no es dueño de nada). Las migraciones corren como `postgres` (`supabase db push`), así que no hay rol de migraciones. Lo crea `backend/scripts/roles.sql`, que se pega una vez en el **SQL editor** de Supabase (idempotente, sin passwords). La password se pone aparte con `\password app_rt` desde `psql`, conectado como `postgres`: el SQL editor guarda los snippets, así que una password escrita ahí queda en el historial. `app_rt` queda con `search_path = public, extensions` y `USAGE` sobre `extensions` (`roles.sql` crea el esquema si no existe, para que vanilla se parezca a Supabase). Cada migración que crea una tabla trae su `GRANT` a `app_rt`.
- **Conexiones:**
  - `DATABASE_URL`: pooler **Supavisor en modo transacción** (puerto 6543), usuario `app_rt.<project-ref>`, `sslmode=require`. Solo en el servicio `api`.
  - credenciales del Supabase CLI: secrets `SUPABASE_ACCESS_TOKEN` y `SUPABASE_DB_PASSWORD`, variable `SUPABASE_PROJECT_REF`. Solo en el job `migrar` de GitHub Actions, desde el Environment `produccion`, limitado a `main`; el job nunca levanta la app (ver `research.md` R1 y R-migraciones).
- **Tenant por `SET LOCAL` dentro de la transacción, nunca `SET` de sesión.** Con el pooler en modo transacción, la conexión física pasa a otro cliente al terminar la transacción: un `SET` de sesión dejaría el tenant de A puesto para B. La unidad de trabajo nace en el slice 2; la regla queda fijada acá porque la impone el pooler.
- **Drift check acotado a `public`:** `compare_metadata` (Alembic solo como librería de test) con `SET search_path TO public, extensions`, sin depender del `search_path` del rol. Los esquemas de Supabase (`auth`, `storage`…) y `supabase_migrations` quedan fuera.
- **Front:** Vite + React + TypeScript, Vitest + Testing Library, Playwright. `VITE_API_URL` por entorno.
- **Railway:** proyecto con 2 servicios (`api`, `web`). `api` con Dockerfile; `web` separado: Dockerfile multi-stage (build con node, Caddy sirve `dist/`; ver `research.md` R5). Dominios públicos generados. Misma región que el proyecto Supabase (o la más cercana).
- **CI (`ci.yml`):** jobs `back` (`migrar_local.sh` desde vacío contra servicio Postgres, uv sync, pytest con el drift check, lint-imports), `front` (npm ci, vitest, build), `seguridad` (pip-audit, npm audit, gitleaks), `evals` (placeholder que pasa), `imagenes` (build de `api` y `web` + `check_imagen.sh`; ver `research.md` R-docker), `migrar` (solo push a `main`, environment `produccion`, después de `back`, `front`, `seguridad` e `imagenes`; `supabase link` + `supabase db push`). Railway con "Wait for CI". `e2e.yml` solo con `workflow_dispatch`. CodeQL y Dependabot por configuración del repo (`.github/dependabot.yml`).
- **import-linter:** en este slice, contrato `forbidden` en `backend/pyproject.toml` contra `googlemaps`, `linkedin*`, `instaloader` y `facebook*`. Los contratos de capas (`dominio` no importa `aplicacion|infraestructura|fastapi|sqlalchemy|httpx`; `aplicacion` no importa `infraestructura|fastapi|sqlalchemy`) entran en el slice 2 con el primer módulo.
- **Secrets:** `.env.example` (ya existe; se suman `CORS_ORIGINS` y `E2E_BASE_URL`) con nombres, nunca valores. Variables de Railway, solo en `api`: `DATABASE_URL`, `CORS_ORIGINS`, `CIFRADO_KEY`, `TYPESAFE_API_KEY`, `CROMA_API_KEY`, `SMTP_*` (cada una se agrega en su slice). `web` recibe solo `VITE_API_URL`. Las credenciales del Supabase CLI viven solo en el GitHub Environment `produccion`, nunca en Railway. Ninguna key de Supabase (anon, service_role, publishable, secret) existe en Railway ni en el repo: no se usan.

## Plan de tareas (TDD, en orden)
El detalle está en `plan.md` → "Orden de tareas". En resumen:
- 0a Supabase: proyecto, `roles.sql` en el SQL editor, `public` fuera de la Data API, `pg_trgm` + `pgcrypto`.
- 0b Railway: `api` + `web`, con el stub de `/health` y su test rojo.
- 1 import-linter con canario.
- 2 guard de arranque, con secrets prohibidos y el Dockerfile de `web`.
- 3 roles + `supabase/migrations` con `migrar_local.sh` + drift acotado a `public` + `test_rol_runtime` + engine sin prepared statements.
- 4 `/health` real.
- 5 front.
- 6 higiene.
- 7 CI.
- 8 Railway completo + E2E.
- 9 protección de `main` + README + docs.

## Riesgos
- Railway tarda en el primer build de Docker: es la tarea 0b, no la última.
- En Supabase, `postgres` **no es superusuario**: es el dueño de `public` y de lo que crea `db push`. **Verificar en 0a** con `\dn+ extensions` que `postgres` es dueño o tiene grant option (si no, el `GRANT USAGE` de `roles.sql` falla en el SQL editor y CI no lo ve), y con `SELECT * FROM pg_default_acl` qué privilegios por defecto de Supabase aplican a `anon`/`authenticated` sobre lo que crea `postgres`.
- `app_rt` sin permisos sobre tablas nuevas: cada migración trae su `GRANT`. El test que prueba que `app_rt` escribe en la tabla nueva entra en el slice 2, con la primera tabla.
- Supabase da a `anon` y `authenticated` privilegios por defecto en `public`. Hoy no hay tablas; el `REVOKE` y su test (`has_table_privilege`) entran con la migración `0002` del slice 2.
- Las migraciones corren antes que el código nuevo: tienen que ser compatibles hacia atrás (expand/contract).
- CI prueba contra `postgres:16` vanilla, no contra Supabase. Lo propio de Supabase (pooler, roles `anon`/`authenticated`) lo prueban `test_engine_desactiva_prepared_statements`, la emulación de roles del slice 2 y el E2E contra el deploy real. El esquema `extensions` lo crea `roles.sql` también en vanilla, y lo cubren `test_rol_runtime` y el test de `pg_trgm` del slice 3.
