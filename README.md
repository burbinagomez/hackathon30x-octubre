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
| Slice | Estado |
|---|---|
| 001 Walking skeleton | pendiente |
| 002 Puertos + registro + croma_supersociedades_co | pendiente |

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
DATABASE_URL=postgresql+psycopg://app_rt@localhost:5432/postgres CORS_ORIGINS=http://localhost:5173 \
  uv run uvicorn app.main:app --reload            # http://localhost:8000/health

# Front (otra terminal)
cd frontend && npm ci
VITE_API_URL=http://localhost:8000 npm run dev    # http://localhost:5173
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

## Fuentes y licencias
Datos de **OpenStreetMap** © colaboradores de OSM, licencia [ODbL](https://opendatacommons.org/licenses/odbl/). Registros de gobierno multi-país vía [Croma](https://usecroma.com/) (Supersociedades, DIAN, RUES, SIEM, SUNAT; datos públicos, no redistribuidos). Datos del **Registro Mercantil** vía Confecámaras / [datos.gov.co](https://www.datos.gov.co/) (dataset `nb3d-v3n7`), licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Las bases derivadas publicadas por este proyecto se comparten bajo las mismas licencias.

## Cumplimiento
Solo se contacta a personas jurídicas por canales que la propia empresa publicó, con identificación, finalidad, origen del dato y opt-out en cada mensaje. Personas naturales se cuentan, no se contactan. Detalle en la skill [`cumplimiento-datos`](.claude/skills/cumplimiento-datos/SKILL.md).

## Licencia del código
MIT (ver `LICENSE`).
