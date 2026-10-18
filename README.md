# Más leads, menor costo — Reto Dapta · 30X Hackathon 2026

Plataforma que encuentra clientes potenciales (pymes) en **fuentes públicas y gratuitas**, los contacta por el canal que la empresa publicó, y mide el **costo por lead (CPL) y por lead calificado (CPQL) de cada fuente y canal**, con cada operación registrada en un libro de costos. Los leads se entregan a Dapta, que los califica.

> Proyecto iniciado tras el kickoff del 30X Hackathon (16 oct 2026). Repo público y open source.

## Cómo se trabaja en este repo
**Nada se desarrolla sin spec, sin reglas, sin agentes y sin skills definidos.**
- Reglas: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- Spec de producto: [`docs/prd.md`](docs/prd.md) · flujo: [`docs/flujo.html`](docs/flujo.html)
- Specs por slice: [`specs/`](specs/)
- Agentes: [`.claude/agents/`](.claude/agents/) · Skills: [`.claude/skills/`](.claude/skills/)
- Contexto para agentes: [`CLAUDE.md`](CLAUDE.md)

## Estado
Verificado contra el código y los tests, no contra los checkboxes de `tasks.md` (que no siempre están al día).

| Slice | Estado |
|---|---|
| 001 Walking skeleton | construido: login (Supabase Auth), tenants con RLS, cifrado de contacto, API y front desplegables |
| 002 Puertos + registro + Supersociedades | construido: puertos, registro por `fuentes.yaml`, `croma_supersociedades_co` (necesita `CROMA_API_KEY`), tope de gasto |
| 003 OSM + dedup | construido: `osm_overpass` y dedup entre fuentes |
| 005 Libro de costos y tablero | construido: costo por operación y tablero por fuente con embudo (solo cuenta jurídicas) |
| 006 Enriquecedor | parcial: `sitio_web` (emails, teléfonos y WhatsApp publicados) y clasificador Jev de encaje operan, con botón "Enriquecer"; `croma_rues_co` es un stub que no verifica (devuelve "desconocido") |
| 008 Dapta y CPQL | construido: exportación CSV de elegibles para Dapta, importación de calificaciones y CPQL por fuente. Sin API de Dapta: va por CSV |
| 010 Intake | construido: Puerta A (formulario), Puerta B (en una frase) y "Ya me compran" (lookalike) |
| 011 datos.gov.co | construido: `datos_gov_co_rues` (dataset `c82u-588k`), solo personas jurídicas activas |
| 014 Marca y responsive | construido: marca, tema, estados de trabajo y e2e de responsive |
| 015 Resultado por fuente | construido: estado por fuente en la respuesta de la búsqueda; una fuente que falla no tumba la búsqueda |
| 007 Email y respuestas | solo spec: no hay código |

## Qué no está
- **No hay contacto por email** (007 es solo spec): ningún mensaje se envía desde esta plataforma. El flag `smtp_email` solo deja elegir "email" como canal preferido. El contacto lo hace la llamada de voz de Dapta, a partir del CSV que exportamos.
- **Los evals no tienen dataset todavía.** El job de CI corre `evals.run --validar`, que valida la forma de la config sin medir nada.
- `croma_dian_trade_co` (descubrimiento por partida arancelaria) está desconectada: no tiene adaptador. `croma_rues_co` no verifica hoy. WhatsApp (009) y Dapta por API no existen.

## Correr local
Necesitás `uv`, Node 22, Docker (solo para Postgres) y `psql`.

```bash
# Postgres local (sin passwords, solo para desarrollo) y el rol de runtime
docker run -d --name pg001 -e POSTGRES_HOST_AUTH_METHOD=trust -p 5432:5432 postgres:16
psql postgresql://postgres@localhost:5432/postgres -f backend/scripts/roles.sql

# Migraciones: supabase/migrations/*.sql en orden, como superusuario
backend/scripts/migrar_local.sh postgresql://postgres@localhost:5432/postgres

# Back
cd backend && uv sync
# CIFRADO_KEY es obligatoria (sin ella la app no arranca): 32 bytes en base64, p. ej.
#   python3 -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
# En Railway va como variable de `api`; nunca en el repo. Perderla deja ilegibles los datos cifrados.
# AUTH_JWKS_URL y AUTH_ISSUER (URLs públicas de Supabase Auth, sin secreto) también son obligatorias en la api; valores de ejemplo:
CIFRADO_KEY=<clave> DATABASE_URL=postgresql+psycopg://app_rt@localhost:5432/postgres CORS_ORIGINS=http://localhost:5173 \
  AUTH_JWKS_URL=https://<ref>.supabase.co/auth/v1/.well-known/jwks.json AUTH_ISSUER=https://<ref>.supabase.co/auth/v1 \
  uv run uvicorn app.main:app --reload            # http://localhost:8000/health

# Front (otra terminal)
cd frontend && npm ci
VITE_API_URL=http://localhost:8000 VITE_SUPABASE_URL=<url> VITE_SUPABASE_PUBLISHABLE_KEY=<publishable> \
  npm run dev                                     # http://localhost:5173
# En Railway, servicio web (variables del build): VITE_API_URL, VITE_SUPABASE_URL y
# VITE_SUPABASE_PUBLISHABLE_KEY. La publishable es pública; la sb_secret_ no va en ningún lado del front.
```

### Migraciones
El esquema vive en `supabase/migrations/NNNN_nombre.sql`: SQL escrito a mano y revisado en el PR. Para un cambio, sumá el archivo siguiente con su `GRANT` a `app_rt` y corré `migrar_local.sh`. Se registra en `supabase_migrations.schema_migrations` y no se reaplica. En producción migra solo el job `migrar` de CI (`supabase db push`) al pushear a `main`. La app nunca migra.

### Tests
```bash
export TEST_DATABASE_URL=postgresql+psycopg://app_rt@localhost:5432/postgres
export TEST_ADMIN_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres
cd backend && uv run pytest -q && uv run lint-imports
cd ../frontend && npm test
```
Los tests de integración fallan, no se saltan, si falta alguna de las dos URLs. Más detalle en [`specs/001-walking-skeleton/quickstart.md`](specs/001-walking-skeleton/quickstart.md).

### CI y required checks
Los checks que `main` exige están en [`.github/required-checks.txt`](.github/required-checks.txt), y `tests/arquitectura/test_required_checks.py` falla si la lista y los workflows se desalinean. CodeQL corre por el default setup de code scanning (publica `Analyze (python)` y `Analyze (javascript-typescript)`), sin workflow propio: con el default setup prendido, GitHub rechaza el SARIF de un `codeql.yml`. `revision-seguridad` corre el agente `security` sobre el diff del PR con el secret `ANTHROPIC_API_KEY` (`.github/scripts/revision_seguridad.sh`; sin el secret, omite la revisión con un warning), y bloquea salvo `Veredicto: PASA` o `Veredicto: PASA CON OBSERVACIONES` (`.github/scripts/veredicto_security.sh`). El agente tiene negado leer `/proc` (`Read(//proc/**)`), y si igual el reporte trae el secret literal, el job lo borra y falla antes de escribir el summary o el artifact. La protección real la verifica el dueño del repo con `.github/scripts/verificar_proteccion.sh <owner/repo>` (necesita `gh` con admin y `jq`).

## Fuentes y licencias
Datos de **OpenStreetMap** © colaboradores de OSM, licencia [ODbL](https://opendatacommons.org/licenses/odbl/). Registros de gobierno multi-país vía [Croma](https://usecroma.com/) (Supersociedades, DIAN, RUES, SIEM, SUNAT; datos públicos, no redistribuidos). Datos del **Registro Mercantil** vía Confecámaras / [datos.gov.co](https://www.datos.gov.co/) (dataset `c82u-588k`), licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Las bases derivadas publicadas por este proyecto se comparten bajo las mismas licencias.

## Cumplimiento
Solo se contacta a personas jurídicas por canales que la propia empresa publicó, con identificación, finalidad, origen del dato y opt-out en cada mensaje. Personas naturales se cuentan, no se contactan. Detalle en la skill [`cumplimiento-datos`](.claude/skills/cumplimiento-datos/SKILL.md).

## Licencia del código
MIT (ver `LICENSE`).
