# Research — 001 Walking skeleton

## R1. Dónde corren las migraciones
- **Decision:** job `migrar` en GitHub Actions, solo en push a `main` y después de `back`, `front` y `seguridad`. Lo corre el GitHub Environment `produccion`, restringido a la rama `main`, con el secret `MIGRATION_DATABASE_URL`. Esa URL usa el TCP proxy público de Railway, el rol `app_mig` (NOSUPERUSER, dueño del schema `public`) y `?sslmode=require`. Railway tiene **"Wait for CI"** activado: despliega solo si CI pasó, migración incluida.
- **Rationale:** `MIGRATION_DATABASE_URL` nunca existe en el entorno de `api` ni de `web` (principio III). El orden queda garantizado: esquema antes que código. Con `app_mig` sin SUPERUSER, una credencial filtrada no puede saltarse RLS ni tocar otros roles.
- **Consecuencia:** las migraciones corren antes que el código nuevo, así que deben ser compatibles hacia atrás (expand/contract). Queda escrito en `docs/arquitectura-backend.md`.
- **Alternatives:** pre-deploy command en `api` (la URL se filtra al runtime); un 4.º servicio `migrate` (la spec fija 3); migrar con `postgres`, que es SUPERUSER y por eso tiene BYPASSRLS (el daño posible es máximo); correr a mano (no es reproducible).
- **Riesgo aceptado:** el TCP proxy expone Postgres a internet, protegido por password y TLS. Se anota en el README. **Verificar en la tarea 0** que el proxy de Railway acepta `sslmode=require`.

## R2. Cómo se prueba "runtime no tiene URL de migraciones"
- **Decision:** dos chequeos.
  1. `test_secrets::test_app_no_arranca_con_url_de_migraciones`: levanta la app con TestClient (lifespan) y `MIGRATION_DATABASE_URL` seteada por `monkeypatch`, y espera el error. Si la variable llega a `api`, el deploy falla al arrancar.
  2. `test_rol_runtime::test_rol_runtime_no_es_super_ni_bypassrls_ni_puede_crear`: conectado con `TEST_DATABASE_URL`, `rolsuper` y `rolbypassrls` de `current_user` deben ser false, y `CREATE TABLE public.x()` debe dar permiso denegado. Cubre el hueco de que alguien ponga la URL del owner en `DATABASE_URL`.
- **Alternatives:** `railway variables --service api --json` en CI (requiere `RAILWAY_TOKEN` en CI, más superficie).

## R3. Roles de base de datos
- **Decision:** `backend/scripts/roles.sql`, idempotente y **sin passwords**. Lo corre `postgres` a mano una vez y hace esto:
  - crea `app_mig` y `app_rt` con `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB`, dentro de un bloque `DO ... IF NOT EXISTS`;
  - `ALTER SCHEMA public OWNER TO app_mig`;
  - `REVOKE CREATE ON SCHEMA public FROM PUBLIC` (explícito aunque PG15 ya lo hace);
  - `GRANT USAGE ON SCHEMA public TO app_rt`;
  - `ALTER DEFAULT PRIVILEGES FOR ROLE app_mig IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rt`;
  - `ALTER DEFAULT PRIVILEGES FOR ROLE app_mig IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_rt`.

  Las passwords se ponen aparte: en producción con `\password app_mig` y `\password app_rt` dentro de psql, que no queda en el historial. En CI van con `ALTER ROLE ... PASSWORD` usando valores de test.
- **Rationale:** `FOR ROLE app_mig` hace que los privilegios apliquen a lo que crean las migraciones, no a quien corrió el script. Con eso no hace falta una plantilla de GRANT por migración.
- **Pendiente para el slice 2:** test de que `app_rt` puede escribir en una tabla creada por `app_mig`. Hoy no hay tablas.
- **Alternatives:** un GRANT explícito en cada migración (se olvida); crear los roles dentro de una migración (la password quedaría en el repo).

## R4. Contratos de import-linter
- **Decision:** contrato `forbidden` sobre `app` contra `googlemaps`, `linkedin*`, `instaloader` y `facebook*`, con `include_external_packages = true`. El test tiene dos casos:
  - **canario:** un paquete mínimo en `tmp_path` con `import googlemaps`, corrido con `lint-imports --config <tmp>`. Espera exit ≠ 0 y el nombre del contrato en la salida;
  - **repo limpio:** exit 0.

  El contrato `layers` entra en el slice 2, con el primer módulo.
- **Rationale:** el rojo tiene que ser una violación detectada, no una config ausente.
- **Verificar en la tarea 1** contra la versión instalada: wildcards en `forbidden_modules` y módulos externos no instalados. Si los wildcards no andan, se listan los nombres explícitos.

## R5. Servicio `web`
- **Decision:** servicio `web` separado, con Dockerfile multi-stage: build con node, después Caddy sirviendo `dist/`. `VITE_API_URL` va como build arg. En `api`, CORS restringido a `CORS_ORIGINS` (el dominio de `web`).
- **Rationale:** la spec fija 3 servicios, y Caddy se configura con una línea.
- **Alternatives:** FastAPI sirviendo el estático (acopla los deploys y rompe los 3 servicios); Railpack autodetectado (menos predecible en el primer build).

## R6. Postgres para tests
- **Decision:** en CI, `services: postgres:16` + `roles.sql` + passwords de test. En local, un `docker run` documentado en el quickstart. `TEST_DATABASE_URL` (`app_rt`) y `TEST_MIGRATION_DATABASE_URL` (`app_mig`) son obligatorios: si faltan, los tests de integración **fallan**, no se saltan.
- **Alternatives:** testcontainers (otra dependencia); SQLite (no es Postgres y no prueba roles).

## R7. Escaneo de secrets
- **Decision:** binario `gitleaks` en el job `seguridad`, sobre el rango del push o del PR. No la action, que pide licencia en orgs.
- **Alternatives:** trufflehog (equivalente; gitleaks es más simple de configurar).

## R8. E2E contra Railway
- **Decision:** `e2e/health.spec.ts` con `E2E_BASE_URL`, en el workflow `e2e.yml` disparado solo con `workflow_dispatch`. El workflow declara el input `base_url` y lo pasa como `E2E_BASE_URL` al step de Playwright. No bloquea el merge.
- **Rationale:** el deploy ocurre después de CI. `deployment_status` depende de que Railway publique deployments en GitHub, y eso no está verificado: se agrega cuando se confirme.

## R9. Alembic sin acoplar a la config de la app
- **Decision:** `alembic/env.py` lee `MIGRATION_DATABASE_URL` de `os.environ` e importa solo `app/modelos.py`, que define `metadata = MetaData()` sin tocar `config`. `target_metadata = metadata`, porque con `None` `alembic check` falla.
- **Rationale:** si `env.py` importara `app.config`, el guard de R2 rompería el job `migrar`, que justamente sí tiene esa variable.
- **En los tests:** `test_upgrade_head_desde_vacio` le pasa `MIGRATION_DATABASE_URL` solo al subproceso de `alembic` (`env=` de `subprocess.run`), nunca al proceso de pytest; si no, cualquier test que levante la app después falla, según el orden. Arranca con `downgrade base` para que "desde vacío" sea cierto.
