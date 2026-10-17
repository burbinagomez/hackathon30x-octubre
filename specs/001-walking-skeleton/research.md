# Research — 001 Walking skeleton

## R1. Dónde corren las migraciones
- **Decision:** job `migrar` en GitHub Actions, solo en push a `main` y después de `back`, `front`, `seguridad` e `imagenes`. Lo corre el GitHub Environment `produccion`, restringido a la rama `main`: `supabase/setup-cli` (pineado) → `supabase link --project-ref $SUPABASE_PROJECT_REF` → `supabase db push`. Secrets `SUPABASE_ACCESS_TOKEN` y `SUPABASE_DB_PASSWORD`; variable `SUPABASE_PROJECT_REF`. Railway tiene **"Wait for CI"** activado: despliega solo si CI pasó, migración incluida. El detalle de la tubería está en R-migraciones.
- **Rationale:** las credenciales de migraciones nunca existen en el entorno de `api` ni de `web` (principio III); el job `migrar` nunca levanta la app. El orden queda garantizado: esquema antes que código.
- **Consecuencia:** las migraciones corren antes que el código nuevo, así que deben ser compatibles hacia atrás (expand/contract). Queda escrito en `docs/arquitectura-backend.md`.
- **Alternatives:** pre-deploy command en `api` (las credenciales se filtran al runtime); un 3.er servicio `migrate` (la spec fija 2); correr a mano (no es reproducible).
- **Riesgo aceptado:** el pooler expone Postgres a internet, protegido por password y TLS. Se anota en el README.

## R2. Cómo se prueba "runtime no tiene URL de migraciones ni keys de Supabase"
- **Decision:** tres chequeos.
  1. `test_secrets::test_app_no_arranca_con_secret_prohibido[…]`: levanta la app con TestClient (lifespan) y cada caso seteado por `monkeypatch`, y espera el error. Los casos:
     - `MIGRATION_DATABASE_URL` (ya no existe, pero el nombre sigue prohibido: defensa en profundidad);
     - un nombre con prefijo `SUPABASE_`;
     - un valor con prefijo `sb_publishable_`, `sb_secret_` o `sbp_` (access token del CLI, la credencial de `migrar`);
     - un JWT (tres segmentos base64url) cuyo payload trae `role` en `{anon, service_role}`;
     - un `DATABASE_URL` con usuario `postgres` o `postgres.<ref>`: la credencial de `migrar` puesta por error en `api`, que saltearía RLS. Solo mira `DATABASE_URL`, porque los tests de integración tienen su admin en `TEST_ADMIN_DATABASE_URL`.
     
     El mensaje nombra la variable y nunca el valor. `test_app_arranca_con_entorno_limpio` evita un guard que rechace todo. Si una key llega a `api`, el deploy falla al arrancar.
  2. `test_rol_runtime::test_rol_runtime_no_es_super_ni_bypassrls_ni_puede_crear`: conectado con `TEST_DATABASE_URL`, `rolsuper`, `rolbypassrls`, `rolcreaterole` y `rolcreatedb` de `current_user` deben ser false; ningún objeto de `pg_namespace` ni `pg_class` tiene dueño `app_rt`; `CREATE TABLE public.x()` debe dar permiso denegado, y `has_schema_privilege('app_rt','extensions','USAGE')` debe ser true (ver spec.md, `test_rol_runtime`). Cubre el hueco de que alguien ponga la URL del owner en `DATABASE_URL`.
  3. `test_secrets::test_dockerfile_web_solo_recibe_vite_api_url`: `web` no corre Python, así que el guard no lo protege. Railway solo pasa al build las variables declaradas como `ARG`, y Caddy no lee el entorno. Si el Dockerfile declara solo `ARG VITE_API_URL`, nada más de Railway puede terminar en el bundle.
- **Por qué el JWT se decodifica y no se busca por forma:** una regla "cualquier JWT" daría falsos positivos con tokens legítimos que lleguen después. Lo que distingue a las keys legacy de Supabase es el claim `role`.
- **Alternatives:** `railway variables --service api --json` en CI (requiere `RAILWAY_TOKEN` en CI, más superficie). Queda como chequeo manual en el quickstart.

## R3. Roles de base de datos
- **Decision:** `backend/scripts/roles.sql`, idempotente y **sin passwords**. En Supabase se pega una vez en el SQL editor (lo corre `postgres`); en CI y local, con `psql -f`. Crea **solo `app_rt`**: las migraciones corren como `postgres` (`supabase db push` en prod, `migrar_local.sh` como superusuario en CI y local), así que no hace falta un rol de migraciones propio. Hace esto:
  - crea `app_rt` con `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB`, dentro de un bloque `DO ... IF NOT EXISTS`;
  - `REVOKE CREATE ON SCHEMA public FROM PUBLIC` (explícito aunque PG15 ya lo hace);
  - `GRANT USAGE ON SCHEMA public TO app_rt`;
  - `CREATE SCHEMA IF NOT EXISTS extensions` (en Supabase ya existe; en vanilla lo crea) y `GRANT USAGE ON SCHEMA extensions TO app_rt`. Qué roles tienen `USAGE` en Supabase se confirma con `\dn+ extensions` en la 0a;
  - `ALTER ROLE app_rt SET search_path = public, extensions`. Supabase instala las extensiones en `extensions`; sin el `search_path` y sin el `USAGE`, `similarity()` del slice 3 no se encuentra.

  La password se pone aparte con `\password app_rt` desde `psql` conectado como `postgres`. No va en el SQL editor, porque guarda los snippets. En CI va con `ALTER ROLE ... PASSWORD` usando un valor de test.
- **Privilegios de `app_rt`:** cada migración que crea una tabla trae su `GRANT SELECT, INSERT, UPDATE, DELETE ON public.<tabla> TO app_rt` (y `USAGE, SELECT` sobre su secuencia, si tiene) en el mismo archivo. Explícito y revisable en el diff; el test del slice 2 que prueba que `app_rt` escribe en la tabla nueva atrapa el olvido.
- **Verificar en 0a:** `\dn+ extensions` (que `postgres` sea dueño o tenga grant option; si no, el `GRANT USAGE` de `roles.sql` falla en el SQL editor y CI no lo ve, porque en vanilla el esquema lo crea `roles.sql`) y `SELECT * FROM pg_default_acl` (qué privilegios por defecto de Supabase aplican a `anon`/`authenticated` sobre lo que crea `postgres`). El resultado define cómo se escribe el `REVOKE` de la `0002`.
- **Pendiente para el slice 2:** test de que `app_rt` puede escribir en la primera tabla, y el `REVOKE` a `anon` y `authenticated` con su test. Hoy no hay tablas.
- **Alternatives:** un rol `app_mig` dueño de `public` con `ALTER DEFAULT PRIVILEGES` (era el diseño con Alembic; `db push` corre como `postgres` y lo deja sin uso); crear los roles dentro de una migración (la password quedaría en el repo).

## R4. Contratos de import-linter
- **Decision:** contrato `forbidden` sobre `app` contra `googlemaps`, `linkedin*`, `instaloader` y `facebook*`, con `include_external_packages = true`. El test tiene dos casos:
  - **canario:** un paquete mínimo en `tmp_path` con `import googlemaps`, corrido con `lint-imports --config <tmp>`. Espera exit ≠ 0 y el nombre del contrato en la salida;
  - **repo limpio:** exit 0.

  El contrato `layers` entra en el slice 2, con el primer módulo.
- **Rationale:** el rojo tiene que ser una violación detectada, no una config ausente.
- **Verificar en la tarea 1** contra la versión instalada: wildcards en `forbidden_modules` y módulos externos no instalados. Si los wildcards no andan, se listan los nombres explícitos.

## R5. Servicio `web`
- **Decision:** servicio `web` separado, con Dockerfile multi-stage: build con node, después Caddy sirviendo `dist/`. `VITE_API_URL` va como build arg y es el único `ARG` (ver R2). En `api`, CORS restringido a `CORS_ORIGINS` (el dominio de `web`).
- **Rationale:** la spec fija 2 servicios (`api`, `web`), y Caddy se configura con una línea.
- **Alternatives:** FastAPI sirviendo el estático (acopla los deploys y deja un solo servicio); Railpack autodetectado (menos predecible en el primer build).

## R-docker. Imágenes multi-stage en `api` y `web`
- **`api`** (`backend/Dockerfile`):
  - **Builder:** `python:3.12-slim`, con `uv` copiado desde `ghcr.io/astral-sh/uv:<tag fijo>`. Corre `uv sync --frozen --no-dev --no-install-project` con `UV_PYTHON_DOWNLOADS=never`, para que el `.venv` use el Python de la imagen, y `UV_LINK_MODE=copy`. `--frozen` exige `uv.lock` commiteado.
  - **Final:** el mismo `python:3.12-slim`, con el mismo `WORKDIR /app`, para que las rutas absolutas del `.venv` sigan valiendo. Copia solo `.venv/` y `app/`, sin `uv` ni compiladores.
  - **Sin pip:** la imagen oficial trae `pip` en `/usr/local`. El final corre `pip uninstall -y pip` antes de `USER`, que borra el paquete de `site-packages` además de los scripts; si borrara solo `/usr/local/bin/pip*`, `python -m pip` seguiría andando. En 3.12 la imagen no trae setuptools. El `ensurepip` que queda no le sirve a un usuario no root sobre `/usr/local`.
  - **Versión de Python:** `uv python pin 3.12`, sin patch. Con `UV_PYTHON_DOWNLOADS=never`, un patch distinto al de la imagen hace fallar `uv sync`.
  - **psycopg:** `psycopg[binary]`, que trae libpq en el wheel, así que no hace falta compilar.
  - **Arranque:** usuario no root (`USER app`) y `CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`. Va en forma shell porque la forma exec no expande `$PORT`. El `HEALTHCHECK` lee el mismo `${PORT:-8000}`.
  - **Las migraciones no corren en el contenedor:** migra el job `migrar` de GitHub Actions (principio IV, R1). La imagen no trae `supabase/`.
- **`web`** (`frontend/Dockerfile`, completa R5):
  - **Etapas:** `node:22-alpine` hace el build. Un stage `caddy:2-alpine`, con el mismo tag fijo, saca la capability. El final es `alpine` con ese binario copiado, y sirve `dist/`.
  - **Caddyfile:**
    - opciones globales `{ admin off }`;
    - sitio `:{$PORT:8080}`, con valor por defecto para `docker run` local y el HEALTHCHECK;
    - `handle /health { respond 200 }`;
    - `handle { root * /srv; try_files {path} /index.html; file_server }`.

    Va con `handle` porque Caddy ordena `try_files` antes que `respond`: sueltos, `/health` se reescribiría a `/index.html`. Y sin `root` + `file_server`, Caddy contesta 200 vacío a todo, aunque `dist/` no exista.
  - **Usuario:** no root, dueño de `/data` y `/config`, que Caddy necesita escribibles.
  - **Capability:** el stage `caddy` corre `apk add libcap` → `setcap -r /usr/bin/caddy`, y el final copia solo el binario. El binario oficial trae `cap_net_bind_service=ep`, y si el runtime no la tiene en el bounding set, el kernel rechaza el exec de un usuario no root. Medido con `--cap-drop ALL`: sin `setcap -r` da `exec /usr/bin/caddy: operation not permitted`. Con el puerto > 1024 la capability no hace falta. `setcap -r` no la otorga, la saca. El job `imagenes` levanta `web` con `--cap-drop ALL` y espera `/health` en 200.
  - **Tamaño (medido el 2026-10-17 con `check_imagen.sh`):** `caddy:2.11.7-alpine` sola pesa 62 MB. Hacer el `setcap` en el final reescribía el binario de 46 MB en otra capa, y la imagen quedaba en 111 MB. Con el binario copiado sobre `alpine:3.23.6` pesa 56 MB, dentro del tope de 60. El final define `XDG_CONFIG_HOME=/config`, `XDG_DATA_HOME=/data` y el `CMD` de la imagen oficial. El `HEALTHCHECK` usa el `wget` de busybox, sin curl.
- **Ambos:**
  - `.dockerignore`, que excluye `.env*`, `.venv`, `node_modules`, `dist`, `tests`, `__pycache__` y `.git`;
  - tags de imagen base fijos (versión exacta; Dependabot `docker` los sube);
  - `HEALTHCHECK` a `/health` sobre `${PORT}` con valor por defecto: en `api` con `python -c "urllib.request…"` (slim no trae curl) y en `web` con el `wget` de busybox.

  Railway usa su propio healthcheck (`healthcheckPath`), así que el `HEALTHCHECK` de la imagen sirve en local y en CI.
- **Check (job `imagenes` en CI):** `.github/scripts/check_imagen.sh <imagen> <max_mb>` falla si la imagen:
  - tiene `node`, `npm`, `uv`, `pip` o `pip3` (`command -v` dentro de la imagen), o si `python -m pip --version` anda;
  - tiene `Config.User` vacío, `root` o `0`;
  - pesa más que `max_mb`: 250 MB para `api`, 60 MB para `web`.

  El script reporta **cada** motivo por nombre, no solo el primero.

  **Rojo**, con un caso por rama y verificando en la salida el motivo nombrado:
  - `python:3.12-slim` pelada, `max_mb=250` → nombra `pip` y `root`;
  - `node:22-alpine` con `max_mb=250` explícito → nombra `node` y `npm`, sin que el tamaño interfiera;
  - `python:3.12-slim`, `max_mb=1` → nombra el tamaño.
- **Orden en CI:** `migrar` tiene `imagenes` en sus `needs`, para que una imagen rota no deje el esquema migrado sin deploy (R1). `imagenes` es *required check* de `main` (principio V).
- **Riesgo:** el límite de 60 MB de `web` está cerca del tamaño de `caddy:2-alpine`. Si no entra, se mide antes de subir el límite.
- **Alternatives:**
  - imagen de una etapa (deja uv, pip y la caché del build en runtime);
  - distroless (sin shell, el check con `command -v` no corre y depurar en Railway se complica).

## R6. Postgres para tests
- **Decision:** en CI, `services: postgres:16` + `roles.sql` + password de test + `migrar_local.sh`. En local, un `docker run` documentado en el quickstart. `TEST_DATABASE_URL` (`app_rt`) y `TEST_ADMIN_DATABASE_URL` (superusuario) son obligatorios: si faltan, los tests de integración **fallan**, no se saltan.
- **Lo que vanilla no tiene:** roles `anon`/`authenticated` y pooler (el esquema `extensions` lo crea `roles.sql`, ver R3). Los roles los emula un script de CI en el slice 2, junto con la primera tabla. El pooler lo cubre `test_engine_desactiva_prepared_statements` (R10) y el E2E contra el deploy real.
- **Alternatives:** testcontainers (otra dependencia); SQLite (no es Postgres y no prueba roles); un proyecto Supabase para CI (otra cuenta y otro secret).

## R7. Escaneo de secrets
- **Decision:** binario `gitleaks` en el job `seguridad`, sobre el rango del push o del PR. No la action, que pide licencia en orgs.
- **Alternatives:** trufflehog (equivalente; gitleaks es más simple de configurar).

## R8. E2E contra Railway
- **Decision:** `e2e/health.spec.ts` con `E2E_BASE_URL`, en el workflow `e2e.yml` disparado solo con `workflow_dispatch`. El workflow declara el input `base_url` y lo pasa como `E2E_BASE_URL` al step de Playwright. No bloquea el merge.
- **Rationale:** el deploy ocurre después de CI. `deployment_status` depende de que Railway publique deployments en GitHub, y eso no está verificado: se agrega cuando se confirme.

## R-migraciones. `supabase/migrations`, `migrar_local.sh` y drift
- **Decision (equipo, 2026-10-17):** la fuente de verdad del esquema es `supabase/migrations/NNNN_nombre.sql`, SQL escrito a mano y revisado por un humano. Nada de `supabase db diff` commiteado sin revisar (principio IV). Reemplaza a Alembic: una sola herramienta de esquema, la del proveedor de la base. El dominio no cambia.
- **Prod:** el job `migrar` (R1) corre `supabase db push`, que aplica en orden lo que falta y lo registra en `supabase_migrations.schema_migrations`. Corre como `postgres`. `supabase/config.toml` lleva solo `project_id`; `supabase/.temp` y `supabase/.branches` van al `.gitignore`. CLI pineado en `ci.yml` (`supabase/setup-cli` + `version`).
- **CI y local:** `backend/scripts/migrar_local.sh <url de superusuario>` aplica los `.sql` en orden con `psql` contra `postgres:16`, como superusuario del servicio (igual que prod). Imita al CLI:
  - registra cada archivo en `supabase_migrations.schema_migrations (version, name)` y saltea lo ya aplicado;
  - el nombre tiene que matchear `^[0-9]+_[a-z0-9_]+$`, o falla (deja `version` y `name` seguros para interpolar);
  - `psql -1 -v ON_ERROR_STOP=1`: el archivo y su registro van en una transacción; si falla, no queda nada a medias y el error nombra el archivo.
- **Drift:** `alembic.autogenerate.compare_metadata` contra `app/modelos.py`, con Alembic solo como librería de test (grupo dev; se borraron `alembic.ini`, `alembic/` y `env.py`). La conexión hace `SET search_path TO public, extensions` antes de comparar: con esquema `None`, la reflexión mira el esquema por defecto, que así queda `public` pase lo que pase con el `search_path` del rol. Los esquemas de Supabase (`auth`, `storage`, `graphql`…) y `supabase_migrations` no entran.
- **Límite conocido:** la reflexión con esquema `None` usa `pg_table_is_visible`, así que también ve `extensions`, que está en el `search_path`. Hoy no trae tablas; el slice 3 necesita `extensions` en el path para `gin_trgm_ops`, así que se deja así.
- **En los tests (`test_migraciones.py`, T017):** cada test crea una base nueva (`DROP/CREATE DATABASE … WITH (FORCE)` + `roles.sql`), así que "desde vacío" es cierto.
  - `test_migrar_local_desde_vacio_dos_veces_sin_drift`: dos corridas en 0, drift vacío y `0001` registrada.
  - `test_aplica_solo_lo_que_falta_y_en_orden`: el caso de prod. `0001` (un `CREATE TABLE` sin `IF NOT EXISTS`) se aplica y se registra; se suma `0002` que altera esa tabla, y la segunda corrida da 0 solo si no reaplica `0001` y aplica `0002` después.
  - `test_aplica_varias_pendientes_en_orden_en_una_corrida`: `0001` y `0002` pendientes a la vez sobre una base vacía; da 0 solo si las aplica en orden.
  - `test_migracion_rota_falla_claro_y_no_deja_nada`: `CREATE TABLE public.u; SELECT 1/0;` → exit ≠ 0, stderr nombra el archivo, `public.u` no existe y no queda la fila `0001` (si quedara, la corrida siguiente saltearía el archivo roto).
  - `test_version_repetida_falla_y_nombra_los_dos`: dos archivos con la misma versión fallan antes de aplicar nada; sin eso, el segundo se saltearía en silencio por estar la versión registrada.
  - `test_nombre_invalido_falla`: prueba el patrón que vuelve seguro interpolar el nombre.
  - `test_drift_mira_solo_public_aunque_cambie_search_path`: con `ajeno.t` y `-c search_path=ajeno,public`, drift vacío; con `public.extra`, drift ≠ vacío.
- **Sin downgrade:** las migraciones SQL solo van hacia adelante. Un error en prod se corrige con una migración nueva (expand/contract).
- **Riesgo a verificar en la primera corrida de `migrar`:** que el CLI llega a la base desde el runner de GitHub (sin IPv6, la conexión directa `db.<ref>.supabase.co` falla; el CLI tiene que entrar por el pooler).
- **Alternatives:** seguir con Alembic (dos herramientas de esquema; el dashboard y el CLI de Supabase no ven sus migraciones); `supabase db diff` como fuente (genera SQL que nadie revisó); `supabase start` en CI para migrar local (levanta todo el stack en Docker: lento y más superficie).

## R10. Pooler en modo transacción y prepared statements
- **Decision:** `api` entra por Supavisor en modo transacción (6543): conexiones cortas, el pool lo maneja Supabase. `db.py` crea el engine con `connect_args={"prepare_threshold": None}`.
- **Rationale:** Supavisor en modo transacción no soporta prepared statements. psycopg 3 prepara una query sola después de `prepare_threshold` ejecuciones (5 por default), así que el error aparece recién con tráfico, no en el primer request. Con `None` no prepara nunca. Fuentes: [psycopg — Prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html), [Supavisor FAQ](https://supabase.github.io/supavisor/faq/), [discussion #28239](https://github.com/orgs/supabase/discussions/28239).
- **Test:** `test_engine_desactiva_prepared_statements` (unit, sin DB) inspecciona los `connect_args` del engine que arma `db.py`. Es un unit porque en CI no hay pooler que reproduzca la falla.
- **Alternatives:** modo sesión también para `api` (pocas conexiones simultáneas por plan; se agota con varios workers); el flag de prepared statements de Supavisor (no se asume activo).

## R11. Tenant por `SET LOCAL`
- **Decision:** el tenant se fija con `SET LOCAL app.tenant_id = …` (o `set_config(..., true)`) dentro de la transacción de la unidad de trabajo. Nunca `SET` de sesión.
- **Rationale:** en modo transacción, la conexión física vuelve al pool de Supavisor al hacer commit y la usa otro cliente. Un `SET` de sesión dejaría el tenant de un request puesto para el siguiente. `SET LOCAL` muere con la transacción.
- **Test:** entra en el slice 2 con la unidad de trabajo. Después del commit, `current_setting('app.tenant_id', true)` en la misma conexión vuelve vacío.

## R12. Vite 6 y Vitest 4 en el front
- **Decision:** `vite@6.4.3` y `vitest@4.1.11`, pin exacto, en lugar de los `vite@5.4.11` y `vitest@2.1.8` de T023. `@vitejs/plugin-react@4.3.4` se queda (acepta `vite ^6`). La config de vitest no cambió: `environment`, `setupFiles` y el `cleanup` explícito de `setupTests.ts` siguen igual.
- **Rationale:** `npm audit --audit-level=high` del job `seguridad` falla con tinypool crítico (≤2.1.1, RCE por prototype pollution), presente en toda la línea vitest 2. `vitest@2.1.9` + `vite@5.4.21`, el fix que sugiere el audit, siguen con tinypool 1.1.1 y suben a 6 hallazgos. Medido el 2026-10-17: la combinación mínima en 0 es vitest 4.1.11 (≤4.1.10 es vulnerable) + vite 6.4.3 (≤6.4.2 es vulnerable). Sin `--omit` ni `overrides`.
- **Test:** `npm audit --audit-level=high` da 0. La suite da 4/4 y vuelve a rojo contra el `App.tsx` sin estado de carga. La imagen web pesa 56 MB de 60.
