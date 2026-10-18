# Traspaso: Reto Dapta (30X)

> **Histórico:** describe el `main` del 2026-10-17 (walking skeleton + 002 base). Hoy el estado verificado está en la tabla "Estado" del `README.md`.

Este documento es para el dev que sigue el trabajo. Antes de tocar nada, leé `CLAUDE.md`, `.specify/memory/constitution.md` y `docs/prd.md`, en ese orden.

El estado que se describe acá es el del 2026-10-17. `main` está en `168f4b9`: el walking skeleton más la 002 base (#22).

## Estrategia: [MIN] primero, Pulido después

El objetivo es que funcione el flujo de punta a punta: login, Nueva búsqueda, OSM y datos.gov.co devuelven leads, los leads se guardan por tenant y se ven en el tablero. En cada `tasks.md`, las tareas marcadas `[MIN]` son las imprescindibles para ese flujo. Las demás son Pulido y van al final. Croma también va al final.

Los checkboxes de `tasks.md` no siempre están al día. Para saber qué está hecho, mirá `git log`: cada tarea tiene un commit `test(...)` en rojo y después uno `feat(...)` en verde.

## Estado por slice

| Slice | Rama | PR | Estado | Depende de |
|---|---|---|---|---|
| 012 seguridad del repo | `feature/012-config-repo` | #23 (borrador) | CI arreglado (`d788170`): sin `codeql.yml`, porque el default setup de CodeQL ya publica Analyze; `revision-seguridad` avisa y sale en 0 si falta `ANTHROPIC_API_KEY` (`.github/scripts/revision_seguridad.sh`) | — |
| 002 puertos + Supersociedades | `feature/002-puertos-registro-supersociedades` | #24 (borrador) | Las tareas [MIN] que faltaban (T021, T023, T025 y T039) están en verde: repositorio de leads, costos en Postgres, `sembrar_tenant.py` y `EjecutarBusqueda` con `lote_id = busqueda_id`. Va a Pulido: T026, T027, T040, T041 (CLI) y T043 (doc) | main |
| 003 OSM + dedup | `feature/003-osm-dedup` | #25 (borrador) | En verde: T012–T015, T037–T041, T044, T047 y T048. Falta del [MIN]: T016a/b, T042, T049, T051, T052, T053 y T055 (cierre). T048b solo si se decide adelantar 002 T034/T035 | 002 en main |
| 011 datos.gov.co (RUES) | `feature/011-datos-gov-co` | #26 (borrador) | T003–T008 en verde. T012 tiene el stub. T013–T016 tienen 4 rojos, marcados con xfail strict. Lo que sigue es T017: el advisor revisa los tests. Después T018 (verde) y la Fase 4 en adelante | 002 en main (puerto de caché, `tests/contratos/fabricas.py`), 005 para el tablero |
| 005 libro de costos + búsqueda | `docs/005-plan` (sin PR) | — | El plan y las tasks tienen APRUEBA del advisor (`7dc6bc4`, 33 [MIN]). P1, P2 y P4 están sin decidir: P1 choca con los estados `terminada`/`con_errores` de la 002 (nota H16) | 002, 003, 011 |
| 014 marca responsive | `feature/014-marca-responsive` (sin PR) | — | Lista. `spec.md:67` sigue en `[ ]` y se cierra con `e2e.yml` contra Railway después del deploy | 012 (fijar SHA de `e2e.yml`) |
| 004 evals | `docs/004-plan-evals` (sin PR) | — | Hay plan, todavía sin implementar | — |

### Ramas pusheadas sin PR y atrasadas respecto de `main`

Quedaron atrasadas a propósito: rebasá o mergeá `origin/main` cuando tomes cada una.

- `docs/005-plan` (7dc6bc4): plan y tasks de la 005, con APRUEBA del advisor y 33 tareas [MIN]. Está 26 commits atrás de `main`.
- `docs/004-plan-evals` (3686a6b): plan de evals de la 004, después de cuatro pasadas del advisor. Está 26 commits atrás de `main`.
- `feature/014-marca-responsive` (c884a3e): marca y layout responsive, con el rojo mobile verificado en local contra `vite preview`. Está 31 commits atrás de `main`.
- `docs/specs-003-004-tasks` (41afa51): lo que queda pendiente de implementar en la 007 y la 008. Está 35 commits atrás de `main`.

## Orden de merge

1. #23 (012)
2. #24 (002)
3. #25 (003)
4. #26 (011)
5. 005

Antes de cada merge, en la rama: `git fetch`, `git merge origin/main` (si hay conflictos, se resuelven a mano y no se fuerzan), las suites en verde y recién ahí push.

### Antes de mergear la 003

El security de la 002 dejó un MEDIUM: `repositorio_leads.py:148-151` guarda `nombre` y `direccion` en claro. Con Supersociedades no hay problema, porque solo trae personas jurídicas. OSM, en cambio, trae `tipo_titular = desconocido`, y ese registro puede ser una persona natural. Hay dos salidas: cifrar esos campos cuando el tipo no sea `juridica`, o dejar la decisión documentada en `docs/decisiones.md`.

## Notas que quedaron abiertas

- **Croma (LOW):** el tope se cuenta por tenant, pero la cuota es de una sola cuenta. Con el tenant único del evento no se nota.
- **`ejecutar_busqueda` (LOW):** si un adaptador tira una excepción que no está prevista, la búsqueda queda en `creada` para siempre.
- **`sembrar_tenant.py` (LOW):** no pide confirmación ni avisa contra qué host va a correr.
- **003, Pulido:**
  - T041q: test del escape del QL.
  - T015p: que `seleccion.py` use `cubre()`.
  - T041p: el timeout escribe su fila y sale como `FuenteNoDisponible`.
- **011:** CLAUDE.md:15 y :42, `constitution.md:38` y `spec.md:143/:272/:279` describen datos.gov.co como "desconectado" o como "verificación + dedup". Eso choca con usarlo para descubrir, y lo tiene que decidir el dueño.

## Cómo correr los tests

```bash
# back
cd backend && uv sync && uv run pytest -q
uv run lint-imports
# front
cd frontend && npm ci && npm test
```

Los tests de integración necesitan `TEST_DATABASE_URL` (rol `app_rt`) y `TEST_ADMIN_DATABASE_URL` (rol `postgres`). Sin esas variables se saltean.

1. Levantá un Postgres 16 efímero en Docker con las mismas variables que el job `back` de `.github/workflows/ci.yml`. Son valores de CI, no secretos de producción.
2. Aplicá las migraciones con `backend/scripts/migrar_local.sh <url-admin-local>`.
3. Exportá las dos URLs locales como las arma `ci.yml`.

Para trabajar en paralelo usamos un contenedor y un puerto por slice:

| Slice | Contenedor | Puerto |
|---|---|---|
| 002 | `pg001` | 5432 |
| 011 | `pg011` | 5434 |
| 003 | `pg003` | 5435 |

El 5433 está ocupado por otro proyecto: no lo toques.

## Reglas que no se negocian

- **Proceso para agilizar (cambio del dueño, 2026-10-17):**
  - El lead corre TDD con rojo real, pero solo los tests de su slice contra su propio Postgres. No corre suite completa, `lint-imports`, front, audits ni `docker build`: eso lo corre el CI.
  - Antes de pushear no se vuelven a correr las suites. El orden es: `fetch` → `merge origin/main` (si hay conflictos, se para y se resuelven a mano) → tests de la slice tocada → push sin `--force`. El CI es el gate completo; si algo falla ahí, se arregla en la rama.
  - Se mantiene: el advisor revisa los rojos antes del Verde, y el security revisa cada PR mientras falte el secret `ANTHROPIC_API_KEY`.
- **Nada sin spec:** no se desarrolla nada sin `specs/NNN-.../spec.md`.
- **TDD con rojo real:** el test falla primero por assert. No sirve que falle por import ni por `NotImplementedError`. Si se marca, va `xfail(strict=True, raises=AssertionError)`. Un test que nace verde necesita un sabotaje con nombre que lo ponga en rojo.
- **Aislamiento por tenant:** RLS con `app.tenant_id` y FKs compuestas `(tenant_id, x_id)`. El `tenant_id` sale del contexto, nunca del input.
- **Sin secretos:** ni en el repo, ni en el front, ni en logs. El contacto se guarda cifrado. Los errores de un adaptador nunca incluyen el cuerpo de la respuesta (`raise ... from None`).
- **El rol `app_rt` no se toca.**
- **Costos:** toda operación de salida escribe una fila en `costos`, con su propia transacción.
- **Hexagonal:** cada fuente y cada canal es un adaptador detrás de un puerto, registrado en `backend/config/fuentes.yaml`.
- **Git:**
  - una rama por slice;
  - nunca `--force`;
  - PRs en borrador;
  - mergea un humano;
  - commits convencionales sin atribución a IA.

## Pendientes humanos

- **Secret `ANTHROPIC_API_KEY`:** cargarlo en el repo. Después hay que volver a hacer que `revision-seguridad` falle si falta: hoy avisa y sale en 0.
- **Railway:** lo maneja Brayan, que es el responsable del deploy y de las variables de entorno.
- **Doc de Dapta:** la documentación de su API para calificar por voz (006/007).
- **T034:** proteger `main` con los checks de `.github/required-checks.txt`. El check de Vercel no entra.
- **005:** decidir P1, P2 y P4.
- **Corte:** si el slice 9 no está el domingo a las 15 h, se corta y queda solo email.
