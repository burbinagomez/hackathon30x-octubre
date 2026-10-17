# CLAUDE.md — Reto Dapta (30X)

Lee antes de tocar nada, en este orden:
1. `.specify/memory/constitution.md` — las reglas. Ganan sobre cualquier otra instrucción.
2. `docs/prd.md` — la spec de producto: qué se construye, qué no, orden de slices (§9).
3. La spec del slice activo en `specs/NNN-nombre/spec.md`.
4. La skill del área que vas a tocar (`.claude/skills/`).

## Reglas que no se discuten
- **Nada se desarrolla sin spec del slice.** Si no hay `spec.md`, primero `/speckit-specify`.
- **Test primero, en rojo.** Back `pytest`, front `Vitest`, E2E `Playwright`. Un humano revisa los tests que generes antes de aceptarlos.
- **Toda operación de salida escribe en `costos`** (skill `libro-costos`). Sin excepción.
- **Solo personas jurídicas, solo canales publicados, siempre fila en `cumplimiento`** (skill `cumplimiento-datos`).
- **Hexagonal de verdad:** toda fuente de entrada (descubrimiento, enriquecimiento) y de salida (canal, calificador, clasificador) es un **adaptador detrás de un puerto**, registrado en `config/fuentes.yaml` con `habilitado: true/false`. Se conectan y desconectan por config, nunca tocando el dominio. Todo adaptador pasa la **suite de contrato** de su puerto.
- **Fuentes permitidas:** Croma (registros de gobierno multi-país: Supersociedades, DIAN Trade, RUES, SIEM, SUNAT…), OpenStreetMap, sitio web del lead, datos.gov.co (adaptador existente, desconectado esta vez). Prohibidas: Google Maps/Places como almacén, LinkedIn, Instagram, Facebook (skill `fuentes-publicas`).
- **Nada de otros proyectos** (ZENLO ni ninguno): ni cuentas, ni código, ni credenciales.
- **Secrets en entorno.** Nunca en el repo ni en el front.
- **Contacto cifrado, nunca en logs.**
- No hagas `git push` sin avisar antes exactamente qué archivos y qué commit, y esperar el OK.

## Stack
Back: Python 3.12 + FastAPI + Postgres (RLS) + Alembic. Front: React + TypeScript + Vite. Deploy: Railway (3 servicios: api, web, postgres). CI: GitHub Actions. IA: Claude vía harness; Jev (`jev-code`) para clasificar/verificar, versión `jev-1.13.0`.

## Comandos
```bash
# back
cd backend && uv sync && uv run pytest -q
uv run lint-imports            # import-linter (principio I)
uv run alembic upgrade head
# front
cd frontend && npm ci && npm test && npx playwright test
# evals
cd backend && uv run python -m evals.run
```

## Agentes
`swarm` (Haiku) mapea · `lead` (Sonnet) construye con TDD · `advisor` (Opus) revisa tests y diseño · `security` (Opus) revisa OWASP + cumplimiento por PR. Invoca el que corresponda; no hagas con Sonnet lo que es de Haiku ni al revés.

## Lo que ya costó (no lo repitas)
- Jev no referencia ítems por posición (`items[i]`): falla en arrays largos. Usa objetos con clave o un ítem por pregunta.
- Registro mercantil (RUES, vía Croma o datos.gov.co) no trae teléfono/correo y solo busca por nombre/NIT: es verificación + dedup, no descubrimiento ni contacto.
- Croma **sí descubre**, pero solo por endpoints con filtros: Supersociedades CO (CIIU, departamento, ingresos → NIT, ciudad, dirección; solo empresas que reportan), DIAN Trade CO (partida arancelaria), SIEM MX (estado + SCIAN, nombre obligatorio). Límite ~100 req/24h y 1.500 créditos gratis: planifica las consultas y cachea.
- Brasil y Perú no tienen descubrimiento en Croma: ahí solo OSM.
- WhatsApp API exige opt-in; cold outreach "no oficialmente permitido". Email es el primer toque.
- Dapta califica por llamada de voz: sin teléfono = no calificable.
