# Constitución — Reto Dapta (30X Hackathon)

> Ubicación: `.specify/memory/constitution.md` · **Versión 1.4.0** · Ratificada 2026-10-17 · 1.1.0: PASS^K en IX · 1.2.0: Postgres en Supabase (III, IV, V) · 1.3.0: límites del front por feature (I) · 1.4.0: migraciones SQL del Supabase CLI (III, IV, V)
> Regla de oro: **una regla entra aquí solo si tiene un chequeo automático que la hace cumplir.** Sin chequeo, es un deseo.
> Regla del proyecto: **nada se desarrolla sin spec, sin reglas, sin agentes y sin skills definidos.** Este archivo es las reglas; `docs/prd.md` es la spec de producto; `.claude/agents/` y `.claude/skills/` son los agentes y skills.

---

## Principios

### I. Hexagonal con barandal — fuentes y salidas conectables
Módulos en `backend/app/modulos/<nombre>/{dominio,aplicacion,infraestructura}`. La dependencia apunta hacia adentro: `dominio/` no importa framework, DB ni clientes externos; `aplicacion/` depende de puertos (Protocols) definidos en `dominio/`; adaptadores viven en `infraestructura/` en archivos separados de sus puertos. Entidades de dominio ≠ modelos de persistencia.
**Toda entrada y salida externa es un adaptador detrás de un puerto**: `FuenteDescubrimiento`, `Enriquecedor`, `CanalContacto`, `Calificador`, `Clasificador`, `RegistroCostos`. Los adaptadores se **registran en `config/fuentes.yaml`** con `habilitado`, `paises`, `filtros` y `trae`; el orquestador carga solo los habilitados que cubren el ICP. Cambiar de fuente (Croma ↔ datos.gov.co, email ↔ WhatsApp, Dapta API ↔ CSV) es un flag, nunca un cambio en dominio ni en casos de uso.
**Front por feature:** `frontend/src/<feature>/`. Una feature importa solo de `compartido/` y `api/`, nunca de otra feature. Lo verifica `eslint-plugin-boundaries` en CI, con canario (`frontend/tests/arquitectura/limites.test.ts`), igual que `import-linter` en el back.
**Chequeo:** `import-linter` con contratos de capas por módulo, en CI. **Suite de contrato por puerto** (`tests/contratos/`), parametrizada sobre todos los adaptadores registrados: cada uno pasa los mismos tests con proveedor falso. Test que falla si un adaptador no está en el registro o si el dominio referencia un adaptador concreto. **Si falla:** sin merge.

### II. El test va primero y en rojo — back y front
Todo cambio de comportamiento empieza con un test que falla. Back: `pytest`. Front: `Vitest` + Testing Library; flujo principal con `Playwright`. Un humano revisa los tests generados por agentes **antes** de aceptarlos.
**Chequeo:** CI corre ambas suites en cada push/PR; PR que toca `src/` sin tocar `tests/` recibe marca para revisión. **Si falla:** sin merge.

### III. Aislamiento por tenant, probado
Toda tabla con datos de un tenant lleva `tenant_id` y RLS activa. El rol de runtime **no** es dueño del esquema ni tiene `BYPASSRLS`; las credenciales de migraciones solo existen en el job `migrar`. El tenant se fija con `SET LOCAL` dentro de la transacción, nunca con `SET` de sesión (el pooler de Supabase en modo transacción reparte conexiones entre clientes). Los roles de Supabase `anon` y `authenticated` no tienen privilegios sobre tablas de `public`.
**Chequeo:** por cada tabla con RLS, test que como tenant B intenta SELECT/UPDATE/DELETE/INSERT sobre datos de A y espera vacío/denegado, corriendo con rol sin `BYPASSRLS`. Test que falla si el entorno de runtime contiene credenciales de migraciones. Test de `has_table_privilege` para `anon` y `authenticated`. **Si falla:** bloqueante absoluto.

### IV. El esquema lo gobiernan las migraciones
Todo cambio de esquema es un `supabase/migrations/NNNN_nombre.sql` escrito a mano y revisado por un humano (nada de `supabase db diff` sin revisar); prod lo aplica `supabase db push` en el job `migrar` y aplicarlas en orden desde base vacía reproduce el esquema.
**Chequeo:** CI levanta Postgres vacío → `scripts/migrar_local.sh` dos veces (la segunda no reaplica) → drift check contra modelos (`compare_metadata`), acotado al esquema `public` (los de Supabase quedan fuera). **Si falla:** sin merge.

### V. Seguridad en el pipeline
Secrets en variables de entorno (Railway para `api`; GitHub Environment `produccion` para las credenciales del Supabase CLI), nunca en el repo ni en el front; `.env*` ignorado. Ninguna key de Supabase (anon, service_role, publishable, secret) existe en el entorno de `api` ni de `web`: la app no arranca si la ve. Dependabot activo. `pip-audit` + `npm audit` (CVE alta/crítica bloquea). CodeQL. Secret scanning + step que falla si el diff introduce un secret. Revisión OWASP Top 10 por PR con el agente `security` (CRITICAL/HIGH bloquea). Toda entrada se valida en el back; texto externo que llegue a un LLM se trata como hostil (prompt injection).
**Chequeo:** los steps son *required checks* de `main`; un test de configuración falla si falta alguno. **Si falla:** sin merge.

### VI. Datos de contacto tratados como sensibles
Teléfonos, correos, nombres de personas y textos de respuesta se **cifran en reposo** (cifrado a nivel de app, clave en entorno) y **nunca aparecen en logs**. Minimización: solo lo que el flujo necesita. Retención definida por tipo.
**Chequeo:** test que recorre el catálogo de columnas sensibles y falla si alguna no está cifrada; test que inyecta valores de prueba y verifica que no salen en logs. **Si falla:** sin merge.

### VII. Cumplimiento por diseño
Solo se contacta a **personas jurídicas** por **canales que la empresa publicó**. Personas naturales se cuentan en el tablero, no se contactan (SIC 17-96489). Cada lead lleva su fila en `cumplimiento`: fuente, licencia, base legal, `as_of`, opt-out. Todo primer mensaje: identificación, finalidad, origen del dato, opt-out, <100 palabras. Fuentes permitidas: Croma (registros de gobierno multi-país), OpenStreetMap, sitio web del lead (robots.txt), datos.gov.co (adaptador desconectado por config). Cada país tiene su marco: Colombia Ley 1581; para MX/PE/BR se documenta la base legal antes de habilitar el adaptador de ese país. **Prohibidas:** Google Maps scraping, Google Places como almacén, LinkedIn, Instagram, Facebook.
**Chequeo:** test que falla si existe un envío a un lead con `tipo_titular != 'juridica'` o sin fila en `cumplimiento`; test de plantilla que falla sin opt-out; `import-linter` prohíbe clientes de las fuentes prohibidas. **Si falla:** bloqueante absoluto.

### VIII. Toda operación escribe su costo
Cada consulta a fuente, fetch web, llamada a LLM/Jev, crédito de Croma, mensaje enviado y minuto de Dapta escribe una fila en `costos` **en el momento en que ocurre**, atribuida al lead o prorrateada. CPL y CPQL se calculan solo desde `costos`. Las tarifas viven en `config/tarifas.yaml`.
**Chequeo:** test de integración que ejecuta cada tipo de operación con proveedor falso y verifica la fila en `costos`; test que falla si un adaptador de salida no pasa por el puerto `RegistroCostos`. **Si falla:** sin merge.

### IX. Lo que no se mide no se declara funcionando
Clasificación de respuestas, encaje ICP y redacción del mensaje tienen set etiquetado versionado en `evals/` (`jev_check`/`jev_classify`, versión pineada `jev-1.13.0`; método en `docs/prd.md` §6b). Umbral mínimo por eval; un cambio que baje la métrica respecto al baseline no mergea sin justificación. **PASS^K con k=3** para LLM-as-judge y para la redacción del mensaje: el caso pasa solo si pasa las 3 corridas. Jev corre con k=1 solo después de demostrar determinación con k=3 sobre el set. Email y teléfono se **verifican antes de enviar**; se reporta tasa usable, no tasa de match.
**Chequeo:** el runner corre local con un comando (`uv run python -m evals.run`), compara con `evals/baseline.json` y sale ≠ 0 si baja; CI invoca ese mismo comando. **Si falla:** sin merge.

### X. Documentación viva y pocas reglas
`README.md` (qué resuelve, cómo correr, variables, tests, atribuciones ODbL/CC BY-SA, badge CI), `docs/arquitectura-backend.md`, `docs/arquitectura-frontend.md`, actualizados en el mismo PR. Comentarios explican el *por qué*. Este archivo no crece por acumulación: una regla nueva trae su chequeo o no entra. Un solo `CLAUDE.md` raíz (<100 líneas) + opcionales en `backend/` y `frontend/`.
**Chequeo:** step de CI marca PR que cambia código de un módulo sin tocar su doc; test de higiene si un `CLAUDE.md` supera 100 líneas. **Si falla:** advertencia; en módulos críticos, bloqueo.

---

## Reglas del proyecto (no negociables)

- **Nada de otros proyectos.** Cuentas, proveedores, código o credenciales de otros proyectos del equipo no se reutilizan. Todo servicio se crea nuevo para el evento. Única excepción: un proveedor de WhatsApp Business API ya existente, **solo si el dueño lo valida por escrito**; mientras tanto, el canal no está disponible.
- **Repo público y open source** desde el primer commit (regla del 30X). Base derivada de OSM/RUES bajo ODbL / CC BY-SA, con atribución.
- **El proyecto empezó tras el kickoff** (16-oct). Nada anterior.
- **Un flujo completo el domingo vale más que cinco a medias.** Si el domingo 3pm el slice 9 (WhatsApp) no está, se corta.

## Flujo de trabajo

**Slice** = cambio vertical acotado que cabe en un PR. Ciclo: `/speckit-specify` (spec corta con "terminado cuando" como test que hoy falla) → `/speckit-plan` → rama por slice → test rojo → verde → refactor → PR con tests + código + doc → **merge cuando CI verde + 1 revisión humana**. Un CI que no corre **bloquea** el merge.

Orden de slices: ver `docs/prd.md` §9.

## Agentes y skills

- `.claude/agents/swarm.md` (Haiku): mapear, buscar, inventariar, generar datos sintéticos. No decide.
- `.claude/agents/lead.md` (Sonnet): escribe test y código del slice con TDD.
- `.claude/agents/advisor.md` (Opus): revisa tests antes de aceptarlos, diseño de puertos, puntos de juicio. No escribe código.
- `.claude/agents/security.md` (Opus): revisión OWASP Top 10 + cumplimiento (principios V–VII) por PR.
- Skills en `.claude/skills/`: `slice-tdd`, `libro-costos`, `cumplimiento-datos`, `fuentes-publicas`. Todo agente las carga antes de tocar el área correspondiente.

## Gobernanza

Cambios a este archivo por PR con etiqueta `constitution` y aprobación del dueño. MAJOR si cambia un principio, MINOR si agrega chequeo, PATCH si aclara. Evadir una regla es el síntoma que este archivo existe para curar: si estorba sin proteger, se enmienda.
