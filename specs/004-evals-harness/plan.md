# Implementation Plan: 004 — Evals harness

**Branch**: `feature/004-evals-harness` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Plan escrito a mano siguiendo el formato de `speckit-plan` (`.specify/templates/plan-template.md`). Por pedido explícito, este slice solo genera `plan.md` y `tasks.md`: sin `research.md`, `data-model.md`, `contracts/` ni `quickstart.md`. Las decisiones que irían ahí ya están en la spec ("Decisiones técnicas") o en las secciones de abajo.

## Summary

Paquete `backend/evals/`, hermano de `app`, que arma el ciclo de PRD §6b: dataset etiquetado → scorers de forma deterministas → juez de significado `{probabilidad, razon}` → runner PASS^3 → comparación con `baseline.json` → código de salida. Entra con dos evals (`encaje_icp`, `juez_mensaje_calibracion`) y un juez real (`JuezClaude`) detrás del puerto `Juez`, con su `RegistroCostos`. El comando de entrada es `uv run python -m evals.run`. Todo lo que el plan no repite está fijado en la spec.

## Technical Context

**Language/Version**: Python 3.12 (el del back)
**Primary Dependencies**: `anthropic` (nueva, con `http_client` de `httpx` inyectable), `httpx` (ya está en dev), `pyyaml` para `evals.yaml` (hoy no está en `uv.lock`; si la 002 no la agrega para `fuentes.yaml`, la agrega este slice), stdlib (`hashlib`, `json`, `re`, `secrets`, `argparse`)
**Storage**: archivos JSON/YAML versionados en `backend/evals/`; filas en `costos` (Postgres, RLS) vía `postgres_costos` del 002
**Testing**: `pytest` (unit, contratos, arquitectura, integración con rol `app_rt`); `httpx.MockTransport` para el juez; `import-linter` para `app` ↛ `evals`
**Target Platform**: local del desarrollador (la corrida real); CI corre solo `pytest` con juez y transporte falsos
**Project Type**: tooling CLI dentro del back; no entra en la imagen de `api` (el Dockerfile copia solo `app/`)
**Performance Goals**: N/A. Llamadas al juez en serie (spec, Fuera del alcance)
**Constraints**: ~2 h de código + ~35 min humanos; ningún dato de contacto en el repo (público); presupuesto de la primera corrida ≈ USD 0.40, avisado antes
**Scale/Scope**: 20–40 casos de encaje + 10–12 de calibración, k=3 → ~126 llamadas por corrida completa

## Constitution Check

*GATE: antes de empezar y re-chequeado al cerrar el diseño.*

| Principio | Qué entrega este slice | Estado |
|---|---|---|
| I Hexagonal | Puerto `Juez` (Protocol) en `evals/jueces/puerto.py`, adaptadores `claude` y `falso` en archivos separados, registro propio en `evals/evals.yaml` (no `config/fuentes.yaml`: tooling, no producto), suite de contrato `tests/contratos/test_juez.py`. Contrato `forbidden` `app` ↛ `evals` con canario. | ✅ |
| II Test primero | Cada tarea de `tasks.md` arranca con su test en rojo; el advisor revisa los de cumplimiento (whitelist, nombre) y las fórmulas del eval (PASS^3, determinación, k=1, baseline). | ✅ |
| III Tenant/RLS | El juez escribe en `costos` con el `tenant_id` del contexto (`--tenant` obligatorio). Las tablas y la unidad de trabajo con `SET LOCAL` son del 002. | ✅ (dep. 002) |
| IV Migraciones | Sin migración. Usa `costos` tal como la deja la `0002` del 002. | — |
| V Seguridad | `ANTHROPIC_API_KEY` del entorno, nunca logueada; los datos del caso van delimitados en `<caso>…</caso>` y escapados (texto externo hostil); `anthropic` pasa por `pip-audit`. | ✅ |
| VI Contacto cifrado | No persiste contacto: la whitelist + regex de `esquema.py` impiden que entre a cualquier JSON de `evals/`. | ✅ |
| VII Cumplimiento | Nombre solo para `juridica` de OSM; Croma sin nombre ni NIT, id aleatorio (`c-` + 12 hex). Atribución ODbL en `evals/LICENCIA.md`. | ✅ |
| VIII Costos | Cada `juzgar` escribe `llm_tokens_in` + `llm_tokens_out` antes de devolver, también cuando la salida es inválida. Test de arquitectura `test_todo_juez_recibe_registro_costos` + integración contra `postgres_costos`. | ✅ (dep. 002) |
| IX Evals | Runner con un comando, PASS^3, `determinacion`, baseline versionado, salida ≠ 0 si baja. **Desvío:** IX dice "CI invoca ese mismo comando" y la spec deja el paso de CI fuera del alcance (ver Complexity Tracking y Pregunta abierta 1). | ⚠️ |
| X Doc viva | Sección de evals en `docs/arquitectura-backend.md` + dos filas en `docs/decisiones.md`. | ✅ |

Re-chequeo post-diseño: sin violaciones nuevas.

## Dependencias externas al slice (no se diseñan acá)

La 002 todavía no tiene plan ni código en `main` (`backend/app/modulos/` está vacío). Este plan **usa** sus piezas por nombre y no fija su forma:

| Id | Qué se necesita | Lo trae | Bloquea |
|---|---|---|---|
| D1 | Protocol `RegistroCostos` y `OperacionCosto` (con `gratis`) en el dominio de `descubrimiento` | 002 | `JuezClaude`, su contrato, `test_todo_juez_recibe_registro_costos` (US1) |
| D2 | `postgres_costos`, migración `0002` (`costos`, `tenants`), unidad de trabajo con `SET LOCAL app.tenant_id` | 002 | integración `test_juez_escribe_filas_llm_en_costos`, composición real de `evals.run`, primera corrida |
| D3 | Carga única de `config/tarifas.yaml` que entrega `costo_unitario` resuelto | 002 | `JuezClaude` (tarifa `llm.claude-sonnet-5-5`) |
| D4 | Puerto `RepositorioLeads` (forma del lead leído) | 002 | `exportar_candidatos` y su repositorio falso |
| D5 | Archivos `tests/arquitectura/test_costos_por_adaptador.py` y `tests/integration/test_costos_repo.py` | 002 (los crea) | la 004 les suma un test a cada uno |
| D6 | Leads de OSM con `tipo_titular` confirmado contra el registro | 003 | exportación real y etiquetado del dataset |
| D7 | Sección `[tool.importlinter]` con el contrato `layers` | 002 | merge: los dos slices tocan el mismo bloque de `pyproject.toml` |

**Qué no espera a nadie:** contrato `app` ↛ `evals`, `esquema.py`, scorers de forma, puerto `Juez` + `JuezFalso`, `config.py`, `fingerprint.py` y el runner con juez falso. Es la Fase 2 de `tasks.md`.

## Diseño

### Puerto y jueces
- `jueces/puerto.py`: `Juez` (Protocol) con `juzgar(tarea, caso) -> Veredicto`; `Veredicto(probabilidad: float, razon: str)` frozen; excepción `SalidaJuezInvalida`.
- `jueces/__init__.py`: `CATALOGO = {"claude": JuezClaude, "falso": JuezFalso}`. Es el único lugar que conoce clases concretas, igual que el catálogo de adaptadores del 002. `jev` se suma en la 006.
- `JuezFalso`: devuelve una secuencia programada por caso y cuenta llamadas por `id`. Sin red, sin `RegistroCostos` (exclusión cerrada del test de arquitectura). Acepta `determinista_si_se_demuestra` en el constructor para el test de k=1.
- `JuezClaude(registro_costos, tarifa, modelo, prompt, http_client)`: SDK `anthropic`, `tool_choice` forzado con `input_schema {probabilidad: number, razon: string}`, temperatura 0. Escribe las 2 filas de costo con `usage` **antes** de validar la salida; después valida y, si no cumple, lanza `SalidaJuezInvalida`.
- `determinista_si_se_demuestra` es atributo de clase del juez (`False` en `claude`); el runner lo lee del catálogo.

### Lo que ya costó con Jev (CLAUDE.md), aplicado desde hoy
- **Un caso por llamada.** El runner nunca manda un array de casos al juez ni pide "el ítem 3". Cada `juzgar` recibe un solo caso como objeto con clave; la respuesta es de ese caso.
- **Todo por clave, nada por posición:** `evals.yaml` es un mapa `nombre_eval → config`; `baseline.json` es un mapa `nombre_eval → {…}`; el reporte identifica fallidos por `id`, no por índice. Cuando la 006 enchufe `jev`, la forma ya sirve.
- La versión de Jev queda pineada en `jev-1.13.0` (`config/tarifas.yaml` y `config/fuentes.yaml`). Cuando la 006 agregue `juez: jev`, su `modelo: jev-1.13.0` entra en el fingerprint: cambiar de versión deja el baseline obsoleto, como debe.

### Runner (`run.py`)
- `main(argv, entorno, fabrica_juez=None, registro_costos=None) -> int`. Los tests inyectan juez y registro falsos; `__main__` arma los reales (D2, D3). El entorno se lee del mapeo inyectado (default `os.environ`), nunca se imprime.
- Orden, tal cual la spec (Flujo principal §3): validar entorno y `evals.yaml` (sale **2** sin construir el juez) → fingerprint por eval → por caso: forma primero, juez k veces solo si la forma pasa → PASS^k → `agregado`, `determinacion`, `fallidos` → comparar con baseline → reporte JSON por stdout → código 0/1/2.
- `lote_id` = un `uuid4` por corrida, el mismo para todas las filas de costo.
- Fórmulas (las revisa el advisor):
  - `agregado = casos_que_pasan / todos_los_casos`;
  - `determinacion = juzgados_con_k_resultados_iguales / juzgados`, `null` si `juzgados == 0`;
  - "pasa la corrida i" = (`probabilidad_i ≥ corte`) == (`etiqueta` positiva).
- k=1 solo si el juez del catálogo tiene `determinista_si_se_demuestra` **y** el baseline vigente, con el mismo fingerprint, es de k=3 con `determinacion == 1.0`. Si no, `ConfigInvalida` → 2. `--actualizar-baseline` con k < 3 → 2.

### Fingerprint (`fingerprint.py`)
`sha256` sobre el JSON canónico (`sort_keys=True`) de: bytes del archivo de casos, bytes del prompt, `modelo`, `corte`, `umbral`. Sin `k` ni `tolerancia`.

### Esquema y whitelist (`esquema.py`)
Una whitelist de claves por archivo (`dataset.json`, `casos/calibracion_mensajes.json`, `baseline.json`), las dos regex (email; teléfono = 7+ dígitos con separadores opcionales) aplicadas a strings **y** a números, exentos cerrados (`id`, `fingerprint`, y `as_of`/`fecha` solo si parsean como ISO 8601), enum `rango_ingresos` y sus cortes en COP. La lista exacta de claves la revisa el advisor (T005).

### Reporte (stdout, JSON)
`{"lote_id", "evals": {"<nombre>": {"agregado", "determinacion", "k", "n", "fingerprint", "umbral", "baseline", "estado", "fallidos": [{"id", "motivo"}]}}, "mejora_sin_fijar": [...]}`. `estado` ∈ `ok`, `bajo_umbral`, `regresion`, `sin_baseline`, `baseline_obsoleto`. Motivos de caso: `forma:<regla>`, `juez_salida_invalida` y, para el caso que falla alguna de las k corridas sin otro motivo, `fallo_corrida` (nombre propuesto; la spec no lo fija).

### Estructura

```text
backend/
├── pyproject.toml                  # + anthropic; contrato forbidden app ↛ evals (root_packages = ["app", "evals"] si hace falta)
├── evals/
│   ├── run.py                      # reemplaza el placeholder
│   ├── config.py · fingerprint.py · esquema.py · exportar_candidatos.py
│   ├── scorers/forma.py
│   ├── jueces/{__init__.py, puerto.py, claude.py, falso.py, encaje_v1.md, mensaje_v1.md}
│   ├── dataset.json · casos/calibracion_mensajes.json · baseline.json · evals.yaml · LICENCIA.md
└── tests/
    ├── unit/evals/{test_dataset.py, test_scorers_forma.py, test_juez_claude.py, test_runner.py, test_exportar_candidatos.py}
    ├── contratos/test_juez.py
    ├── arquitectura/{test_import_linter.py, test_costos_por_adaptador.py}   # se les suma un test
    └── integration/test_costos_repo.py                                      # se le suma un test
.gitignore                          # + backend/evals/dataset.candidatos.json
docs/{arquitectura-backend.md, decisiones.md}
```

**Gotcha de pytest:** `tests/unit/evals/` va **sin** `__init__.py`. Con uno, pytest lo importa como paquete `evals` y tapa al `backend/evals/` real.

**Structure Decision**: la de la spec (Decisiones técnicas, "Ubicación"). Lo único que suma el plan es `jueces/__init__.py` (catálogo).

## Orden de tareas (TDD)

El de la spec, partido por dependencias (detalle en `tasks.md`):
1. **Sin dependencias (Fase 2):** contrato `app` ↛ `evals` → esquema/whitelist (advisor) → scorers de forma → puerto + `JuezFalso` + runner (advisor).
2. **Con D1–D5 (US1):** `JuezClaude` + contrato + arquitectura (advisor de costos) → integración → exportación → etiquetado humano (D6) → primera corrida y baseline de `encaje_icp`.
3. **US2, cortable:** calibración sintética + etiquetado + `mensaje_v1.md` + baseline de `juez_mensaje_calibracion`. Si no entra, pasa a la 007 con `test_calibracion_valida`.
4. **Cierre:** docs, decisiones, job `evals` de CI (Pregunta abierta 1).

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| El job `evals` de CI no corre la corrida real (IX dice "CI invoca ese mismo comando") | La spec lo deja fuera: la corrida real necesita `ANTHROPIC_API_KEY`, una base con `costos` y un tenant, y gasta. Los tests del harness sí corren en `back` con juez falso | Poner la API key y una base en CI ahora: más secrets y gasto por push para un chequeo que este fin de semana es local + baseline commiteado (PRD §6b) |
| Juez fuera de `config/fuentes.yaml` | Es tooling: nunca corre en el pipeline de leads. Igual tiene puerto, contrato y `RegistroCostos` (spec) | Registrarlo como `clasificadores.*`: mezclaría producto con medición |
| `JuezFalso` exento de `RegistroCostos` | No sale a la red; exclusión cerrada y nombrada en el test | Darle un registro que nunca escribe: test de arquitectura que nace verde |

## Preguntas abiertas

1. **Job `evals` de CI (bloquea el merge, no el arranque).** Hoy corre `uv run python -m evals.run` sobre el placeholder y es required check. Con el runner real sale 2 (sin API key ni tenant) y deja `main` en rojo. Hay que elegir entre que el job pase a correr los tests del harness con juez falso, que el job se quite de los required checks hasta que haya corrida en CI, o que se le dé a CI la key y una base. La spec no lo decide.
2. **`anthropic` en `dev` o en `dependencies`.** Por defecto va en `dev`: `evals/` no entra en la imagen de `api`. La 007 lo mueve a `dependencies` cuando el redactor lo use desde `app`.
3. **Qué archivo de casos usa cada eval.** La spec lista las claves de `evals.yaml` sin `casos`. Por defecto se agrega `casos: <ruta>` por eval: el runner lo necesita y el fingerprint ya hashea el contenido. Si el dueño prefiere un mapa fijo en código, es un cambio de una línea.
4. **`docs/arquitectura-backend.md` no existe en `main`.** El 001 dejó su creación a la 013. Por defecto la 004 lo crea con solo la sección de evals, y la 013 lo consolida.
5. **Orden de merge con la 002** (D7): las dos tocan `[tool.importlinter]`. Lo simple es que la 004 se rebasee sobre la 002.
