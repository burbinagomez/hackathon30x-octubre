# Research — 001 Walking skeleton

## R1. Dónde corren las migraciones
- **Decision:** job `migrar` en GitHub Actions, solo en push a `main` y después de `back`, `front`, `seguridad` e `imagenes`. Lo corre el GitHub Environment `produccion`, restringido a la rama `main`, con el secret `MIGRATION_DATABASE_URL`. Esa URL entra al **pooler de Supabase en modo sesión** (`aws-0-<region>.pooler.supabase.com:5432`) con el usuario `app_mig.<project-ref>` (NOSUPERUSER, dueño del schema `public`) y `?sslmode=require`. Railway tiene **"Wait for CI"** activado: despliega solo si CI pasó, migración incluida.
- **Por qué no la conexión directa:** `db.<ref>.supabase.co:5432` resuelve solo a IPv6 si no se paga el add-on IPv4, y los runners de GitHub Actions no tienen IPv6: la conexión falla con "Network is unreachable". El pooler en modo sesión es IPv4 en todos los planes y, a diferencia del modo transacción, soporta DDL, prepared statements y sesiones largas: sirve para Alembic. Fuentes: [Supabase — Connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres), [discussion #20955](https://github.com/orgs/supabase/discussions/20955), [discussion #43111](https://github.com/orgs/supabase/discussions/43111).
- **Rationale:** `MIGRATION_DATABASE_URL` nunca existe en el entorno de `api` ni de `web` (principio III). El orden queda garantizado: esquema antes que código. Con `app_mig` sin SUPERUSER, una credencial filtrada no puede saltarse RLS ni tocar otros roles.
- **Consecuencia:** las migraciones corren antes que el código nuevo, así que deben ser compatibles hacia atrás (expand/contract). Queda escrito en `docs/arquitectura-backend.md`.
- **Alternatives:** conexión directa con el add-on IPv4 de Supabase (pago; mismo resultado); pre-deploy command en `api` (la URL se filtra al runtime); un 3.er servicio `migrate` (la spec fija 2); migrar con `postgres` (es el admin del proyecto: el daño posible es máximo); correr a mano (no es reproducible).
- **Riesgo aceptado:** el pooler expone Postgres a internet, protegido por password y TLS. Se anota en el README. **Verificar en la tarea 0a** que el pooler acepta roles propios (`app_mig.<ref>`, `app_rt.<ref>`) y `sslmode=require`.

## R2. Cómo se prueba "runtime no tiene URL de migraciones ni keys de Supabase"
- **Decision:** tres chequeos.
  1. `test_secrets::test_app_no_arranca_con_secret_prohibido[…]`: levanta la app con TestClient (lifespan) y cada caso seteado por `monkeypatch`, y espera el error. Los casos:
     - `MIGRATION_DATABASE_URL`;
     - un nombre con prefijo `SUPABASE_`;
     - un valor con prefijo `sb_publishable_` o `sb_secret_`;
     - un JWT (tres segmentos base64url) cuyo payload trae `role` en `{anon, service_role}`.
     
     El mensaje nombra la variable y nunca el valor. `test_app_arranca_con_entorno_limpio` evita un guard que rechace todo. Si una key llega a `api`, el deploy falla al arrancar.
  2. `test_rol_runtime::test_rol_runtime_no_es_super_ni_bypassrls_ni_puede_crear`: conectado con `TEST_DATABASE_URL`, `rolsuper`, `rolbypassrls`, `rolcreaterole` y `rolcreatedb` de `current_user` deben ser false; ningún objeto de `pg_namespace` ni `pg_class` tiene dueño `app_rt`; `CREATE TABLE public.x()` debe dar permiso denegado, y `has_schema_privilege('app_rt','extensions','USAGE')` debe ser true (ver spec.md, `test_rol_runtime`). Cubre el hueco de que alguien ponga la URL del owner en `DATABASE_URL`.
  3. `test_secrets::test_dockerfile_web_solo_recibe_vite_api_url`: `web` no corre Python, así que el guard no lo protege. Railway solo pasa al build las variables declaradas como `ARG`, y Caddy no lee el entorno. Si el Dockerfile declara solo `ARG VITE_API_URL`, nada más de Railway puede terminar en el bundle.
- **Por qué el JWT se decodifica y no se busca por forma:** una regla "cualquier JWT" daría falsos positivos con tokens legítimos que lleguen después. Lo que distingue a las keys legacy de Supabase es el claim `role`.
- **Alternatives:** `railway variables --service api --json` en CI (requiere `RAILWAY_TOKEN` en CI, más superficie). Queda como chequeo manual en el quickstart.

## R3. Roles de base de datos
- **Decision:** `backend/scripts/roles.sql`, idempotente y **sin passwords**. En Supabase se pega una vez en el SQL editor (lo corre `postgres`); en CI y local, con `psql -f`. Hace esto:
  - crea `app_mig` y `app_rt` con `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB`, dentro de un bloque `DO ... IF NOT EXISTS`;
  - `GRANT app_mig TO CURRENT_USER`: en Supabase `postgres` no es superusuario, y para cambiar el dueño de un objeto hay que poder hacer `SET ROLE` al nuevo dueño. En vanilla es inocuo;
  - `ALTER SCHEMA public OWNER TO app_mig`;
  - `REVOKE CREATE ON SCHEMA public FROM PUBLIC` (explícito aunque PG15 ya lo hace);
  - `GRANT USAGE ON SCHEMA public TO app_rt`;
  - `ALTER DEFAULT PRIVILEGES FOR ROLE app_mig IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rt`;
  - `ALTER DEFAULT PRIVILEGES FOR ROLE app_mig IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_rt`;
  - `CREATE SCHEMA IF NOT EXISTS extensions` (en Supabase ya existe; en vanilla lo crea) y `GRANT USAGE ON SCHEMA extensions TO app_rt, app_mig`. El `GRANT` es inocuo si el rol ya tiene `USAGE`; qué roles lo tienen en Supabase se confirma con `\dn+ extensions` en la 0a;
  - `ALTER ROLE app_mig SET search_path = public, extensions` y lo mismo para `app_rt`. Supabase instala las extensiones en `extensions`; sin el `search_path` y sin el `USAGE`, `similarity()` del slice 3 no se encuentra.

  Las passwords se ponen aparte con `\password app_mig` y `\password app_rt` desde `psql` conectado como `postgres` por el pooler en modo sesión. No van en el SQL editor, porque guarda los snippets. En CI van con `ALTER ROLE ... PASSWORD` usando valores de test.
- **Rationale:** `FOR ROLE app_mig` hace que los privilegios apliquen a lo que crean las migraciones, no a quien corrió el script. Con eso no hace falta una plantilla de GRANT por migración.
- **Verificar en 0a:** `\dn+ public` (dueño `app_mig`), `\dn+ extensions` (que `postgres` sea dueño o tenga grant option; si no, el `GRANT USAGE` de `roles.sql` falla en el SQL editor y CI no lo ve, porque en vanilla el esquema lo crea `roles.sql`) y `SELECT * FROM pg_default_acl` (qué privilegios por defecto de Supabase siguen aplicando a `anon`/`authenticated`). El resultado define cómo se escribe el `REVOKE` de la `0002`.
- **Pendiente para el slice 2:** test de que `app_rt` puede escribir en una tabla creada por `app_mig`, y el `REVOKE` a `anon` y `authenticated` con su test. Hoy no hay tablas.
- **Alternatives:** un GRANT explícito en cada migración (se olvida); crear los roles dentro de una migración (la password quedaría en el repo).

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
  - **Alembic no corre en el contenedor:** migra el job `migrar` de GitHub Actions (principio IV, R1).
- **`web`** (`frontend/Dockerfile`, completa R5):
  - **Etapas:** `node:22-alpine` hace el build y `caddy:2-alpine` sirve `dist/`.
  - **Caddyfile:**
    - opciones globales `{ admin off }`;
    - sitio `:{$PORT:8080}`, con valor por defecto para `docker run` local y el HEALTHCHECK;
    - `handle /health { respond 200 }`;
    - `handle { root * /srv; try_files {path} /index.html; file_server }`.

    Va con `handle` porque Caddy ordena `try_files` antes que `respond`: sueltos, `/health` se reescribiría a `/index.html`. Y sin `root` + `file_server`, Caddy contesta 200 vacío a todo, aunque `dist/` no exista.
  - **Usuario:** no root, dueño de `/data` y `/config`, que Caddy necesita escribibles.
  - **Capability:** en el build, `apk add libcap` → `setcap -r /usr/bin/caddy` → `apk del libcap`. El binario oficial trae `cap_net_bind_service`, y como no root, un runtime que bloquee file capabilities hace fallar el exec recién en Railway. Con el puerto > 1024 no hace falta.
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
- **Decision:** en CI, `services: postgres:16` + `roles.sql` + passwords de test. En local, un `docker run` documentado en el quickstart. `TEST_DATABASE_URL` (`app_rt`) y `TEST_MIGRATION_DATABASE_URL` (`app_mig`) son obligatorios: si faltan, los tests de integración **fallan**, no se saltan.
- **Lo que vanilla no tiene:** roles `anon`/`authenticated` y pooler (el esquema `extensions` lo crea `roles.sql`, ver R3). Los roles los emula un script de CI en el slice 2, junto con la primera tabla. El pooler lo cubre `test_engine_desactiva_prepared_statements` (R10) y el E2E contra el deploy real.
- **Alternatives:** testcontainers (otra dependencia); SQLite (no es Postgres y no prueba roles); un proyecto Supabase para CI (otra cuenta y otro secret).

## R7. Escaneo de secrets
- **Decision:** binario `gitleaks` en el job `seguridad`, sobre el rango del push o del PR. No la action, que pide licencia en orgs.
- **Alternatives:** trufflehog (equivalente; gitleaks es más simple de configurar).

## R8. E2E contra Railway
- **Decision:** `e2e/health.spec.ts` con `E2E_BASE_URL`, en el workflow `e2e.yml` disparado solo con `workflow_dispatch`. El workflow declara el input `base_url` y lo pasa como `E2E_BASE_URL` al step de Playwright. No bloquea el merge.
- **Rationale:** el deploy ocurre después de CI. `deployment_status` depende de que Railway publique deployments en GitHub, y eso no está verificado: se agrega cuando se confirme.

## R9. Alembic sin acoplar a la config de la app, y acotado a `public`
- **Decision:** `alembic/env.py` lee `MIGRATION_DATABASE_URL` de `os.environ` e importa solo `app/modelos.py`, que define `metadata = MetaData()` sin tocar `config`. `target_metadata = metadata`, porque con `None` `alembic check` falla.
- **Acotado a `public`:** al abrir la conexión, `env.py` hace `SET search_path TO public, extensions`. Con `include_schemas=False` (el default), Alembic compara solo el esquema por defecto, que así queda `public` pase lo que pase con el `search_path` del rol, y `alembic_version` se crea ahí. **No** se setea `version_table_schema`: Alembic compara el esquema `None` y solo descarta `alembic_version` si el esquema comparado es igual a `version_table_schema` (`alembic/autogenerate/compare.py`, `_autogen_for_tables`). Con `"public"`, `None != "public"` y `alembic check` vería `alembic_version` como tabla sobrante siempre. Los esquemas de Supabase (`auth`, `storage`, `graphql`…) no entran al drift.
- **Límite conocido:** la reflexión con esquema `None` usa `pg_table_is_visible`, así que también ve `extensions`, que está en el `search_path`. Hoy no trae tablas; el slice 3 necesita `extensions` en el path para `gin_trgm_ops`, así que se deja así.
- **Rationale:** si `env.py` importara `app.config`, el guard de R2 rompería el job `migrar`, que justamente sí tiene esa variable.
- **En los tests:**
  - `test_upgrade_head_desde_vacio` le pasa `MIGRATION_DATABASE_URL` solo al subproceso de `alembic` (`env=` de `subprocess.run`), nunca al proceso de pytest; si no, cualquier test que levante la app después falla, según el orden. Arranca con `downgrade base` para que "desde vacío" sea cierto.
  - `test_drift_mira_solo_public_aunque_cambie_search_path` crea `ajeno.t` y corre el subproceso con `PGOPTIONS="-c search_path=ajeno,public"`. Espera `alembic check` en 0 y `alembic_version` en `public`. Después crea una tabla extra en `public` y espera `alembic check` ≠ 0. Sin el `SET search_path` de `env.py`, el esquema por defecto sería `ajeno` y el test falla: nace rojo.

## R10. Pooler en modo transacción y prepared statements
- **Decision:** `api` entra por Supavisor en modo transacción (6543): conexiones cortas, el pool lo maneja Supabase. `db.py` crea el engine con `connect_args={"prepare_threshold": None}`.
- **Rationale:** Supavisor en modo transacción no soporta prepared statements. psycopg 3 prepara una query sola después de `prepare_threshold` ejecuciones (5 por default), así que el error aparece recién con tráfico, no en el primer request. Con `None` no prepara nunca. Fuentes: [psycopg — Prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html), [Supavisor FAQ](https://supabase.github.io/supavisor/faq/), [discussion #28239](https://github.com/orgs/supabase/discussions/28239).
- **Test:** `test_engine_desactiva_prepared_statements` (unit, sin DB) inspecciona los `connect_args` del engine que arma `db.py`. Es un unit porque en CI no hay pooler que reproduzca la falla.
- **Alternatives:** modo sesión también para `api` (pocas conexiones simultáneas por plan; se agota con varios workers); el flag de prepared statements de Supavisor (no se asume activo).

## R11. Tenant por `SET LOCAL`
- **Decision:** el tenant se fija con `SET LOCAL app.tenant_id = …` (o `set_config(..., true)`) dentro de la transacción de la unidad de trabajo. Nunca `SET` de sesión.
- **Rationale:** en modo transacción, la conexión física vuelve al pool de Supavisor al hacer commit y la usa otro cliente. Un `SET` de sesión dejaría el tenant de un request puesto para el siguiente. `SET LOCAL` muere con la transacción.
- **Test:** entra en el slice 2 con la unidad de trabajo. Después del commit, `current_setting('app.tenant_id', true)` en la misma conexión vuelve vacío.
