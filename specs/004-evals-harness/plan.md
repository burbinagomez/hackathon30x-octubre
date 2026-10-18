# Implementation Plan: 004 — Evals harness

**Branch**: `feature/004-evals-harness` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Plan escrito a mano siguiendo el formato de `speckit-plan` (`.specify/templates/plan-template.md`). Por pedido explícito, este slice solo genera `plan.md` y `tasks.md`: sin `research.md`, `data-model.md`, `contracts/` ni `quickstart.md`. Las decisiones que irían ahí ya están en la spec ("Decisiones técnicas") o en las secciones de abajo.

## Summary

Paquete `backend/evals/`, hermano de `app`, que arma el ciclo de PRD §6b: dataset etiquetado → scorers de forma deterministas → juez de significado `{probabilidad, razon}` → runner PASS^3 → comparación con `baseline.json` → código de salida. Entra con dos evals (`encaje_icp`, `juez_mensaje_calibracion`) y un juez real (`JuezClaude`) detrás del puerto `Juez`, con su `RegistroCostos`. El comando de entrada es `uv run python -m evals.run`. Todo lo que el plan no repite está fijado en la spec.

## Technical Context

**Language/Version**: Python 3.12 (el del back)
**Primary Dependencies**: `httpx` (ya está en `dependencies`; el juez la usa directo, sin SDK `anthropic`, decisión T017), `pyyaml` en `dependencies` (la 002 la usa en runtime para `fuentes.yaml`; la 002 y la 012 declaran la misma línea), stdlib (`hashlib`, `json`, `re`, `secrets`, `argparse`)
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
| V Seguridad | `ANTHROPIC_API_KEY` del entorno (la lee la composición y entra por constructor), nunca logueada; los datos del caso van delimitados en `<caso>…</caso>` y escapados (texto externo hostil); sin SDK nuevo, `pip-audit` limpio. | ✅ |
| VI Contacto cifrado | No persiste contacto: la whitelist + regex de `esquema.py` impiden que entre a cualquier JSON de `evals/`. | ✅ |
| VII Cumplimiento | Nombre solo para `juridica` de OSM; Croma sin nombre ni NIT, id aleatorio (`c-` + 12 hex). Atribución ODbL en `evals/LICENCIA.md`. | ✅ |
| VIII Costos | Cada `juzgar` escribe `llm_tokens_in` + `llm_tokens_out` antes de devolver, también cuando la salida es inválida. Test de arquitectura `test_todo_juez_recibe_registro_costos` + integración contra `postgres_costos`. | ✅ (dep. 002) |
| IX Evals | Runner con un comando, PASS^3, `determinacion`, baseline versionado, salida ≠ 0 si baja. **Desvío:** IX dice "CI invoca ese mismo comando" y la spec deja el paso de CI fuera del alcance : el job `evals` corre los tests del harness con el juez falso (decisión Q1, ver Complexity Tracking). | ⚠️ |
| X Doc viva | Sección de evals en `docs/arquitectura-backend.md` + dos filas en `docs/decisiones.md`. | ✅ |

Re-chequeo post-diseño: sin violaciones nuevas.

## Dependencias externas al slice (no se diseñan acá)

Corrección (T011): cuando se escribió este plan la 002 no estaba en `main`; hoy sí lo está (`main` en `e113dbd`), así que la mayoría de estas piezas ya existen. Este plan las **usa** por nombre y no fija su forma. Estado verificado contra `main`:

| Id | Qué se necesita | Lo trae | Bloquea | Estado en `main` |
|---|---|---|---|---|
| D1 | Protocol `RegistroCostos` y `OperacionCosto` (con `gratis`) en `app/modulos/costos/dominio/` (`puertos.py`, `modelos.py`; divergencia: el plan decía `descubrimiento`, la 002 lo dejó en su propio módulo `costos`). El Protocol pide **además** `requests_24h` y `creditos_mes` (`puertos.py:7-14`): el contrato de T015 y todo falso que se tipe como `RegistroCostos` tiene que cubrirlos, no solo `registrar` | 002 | `JuezClaude`, su contrato, `test_todo_juez_recibe_registro_costos` (US1) | existe |
| D2 | `postgres_costos`, migración `0002` (`costos`, `tenants`), unidad de trabajo con `SET LOCAL app.tenant_id` | 002 | integración `test_juez_escribe_filas_llm_en_costos`, composición real de `evals.run`, primera corrida | existe: `PostgresCostos(engine, tenant_id)` y `app/db.py::unidad_de_trabajo` |
| D3 | Carga única de `config/tarifas.yaml` que entrega `costo_unitario` resuelto | 002 | `JuezClaude` (tarifa `llm.claude-sonnet-5-5`) | parcial: solo `_cargar_tarifas()` privado en `app/cli.py`, sin la sección `llm` (que sí está en `tarifas.yaml`). T019 tiene que exponerlo o leer `llm` aparte |
| D4 | Puerto `RepositorioLeads` (forma del lead leído) | 002 | `exportar_candidatos` y su repositorio falso | existe en `descubrimiento/dominio/puertos.py` |
| D5 | Archivos `tests/arquitectura/test_costos_por_adaptador.py` y `tests/integration/test_costos_repo.py` | 002 (los crea) | la 004 les suma un test a cada uno | parcial: existe `test_costos_repo.py`; `test_costos_por_adaptador.py` **no**, lo crea T013 |
| D6 | Leads de OSM con `tipo_titular` confirmado contra el registro | 003 | exportación real y etiquetado del dataset | — |
| D7 | Sección `[tool.importlinter]` con el contrato `layers` | 002 | merge: los dos slices tocan el mismo bloque de `pyproject.toml` | existe (contrato "Capas de los modulos" junto a "App no importa evals") |

**T034:** su premisa ("después de que la 002 esté en `main`") ya se cumple: la rama sale de `main` con la 002 adentro, `pyproject.toml` tiene una sola línea de `pyyaml` en `dependencies` y `uv lock --check` pasa. Queda como verificación antes del merge, no como merge pendiente.

**Qué no espera a nadie:** contrato `app` ↛ `evals`, `esquema.py`, scorers de forma, puerto `Juez` + `JuezFalso`, `config.py`, `fingerprint.py` y el runner con juez falso. Es la Fase 2 de `tasks.md`.

## Diseño

### Puerto y jueces
- `jueces/puerto.py`: `Juez` (Protocol) con `juzgar(tarea, caso) -> Veredicto`; `Veredicto(probabilidad: float, razon: str)` frozen; excepción `SalidaJuezInvalida`.
- `jueces/catalogo.py`: `CATALOGO = {"claude": JuezClaude, "falso": JuezFalso}`. Es el único lugar que conoce clases concretas, igual que el catálogo de adaptadores del 002. `jev` se suma en la 006. **No va en `jueces/__init__.py`** (regla del coordinador, Fase 3): `run.py` importa `evals.jueces.puerto` y eso ejecuta el `__init__`, así que cualquier import de `JuezClaude` ahí se cargaría en cada corrida, también en los tests del runner. `__init__.py` queda vacío; `catalogo.py` se importa solo en la rama por defecto de `run.py` (T019).
- Tarifa del juez (T017): el mapeo de `tarifas.yaml` `llm.<modelo>`, `{"in_usd_por_M": Decimal, "out_usd_por_M": Decimal}`. El juez divide por el **entero** `1_000_000` al escribir `costo_unitario` (nunca por `1e6`, que es float); su rojo es `test_registra_costos_antes_de_devolver[sonnet|haiku]` (T018; haiku: `0.10` → `Decimal("0.0000001")`). La conversión del yaml es `Decimal(str(v))`, nunca `Decimal(v)` sobre el float, y la hace la composición: su rojo va en T019.
- Key de Anthropic (decisión del dueño, T017): parámetro `api_key` explícito y `httpx` directo, sin SDK. `JuezClaude` nunca lee el entorno: recibe la key por constructor, usa el `httpx.Client` inyectado y pone `x-api-key` (y `anthropic-version`) en cada request. En T019 la key sale del mapeo `entorno` de `main()` (default `os.environ`); si falta, sale 2 (ya cubierto por `test_sin_entorno_sale_2_sin_llamar`).
- Fixture compartida de la Messages API falsa: `backend/tests/anthropic_falso.py` (T014–T017): `httpx.MockTransport` sin headers propios (solo `base_url` y transporte) que captura el cuerpo JSON y `dict(request.headers)` de `POST /v1/messages`, y responde `tool_use` con `usage` 120/30, un `content` propio (p. ej. `SIN_TOOL_USE`) o una respuesta HTTP entera (p. ej. un 401). Key falsa: `CLAVE_FALSA = "sk-ant-test-XXXX"`.
- `JuezFalso`: devuelve una secuencia programada por caso y cuenta llamadas por `id`. Sin red, sin `RegistroCostos` (exclusión cerrada del test de arquitectura).
- `JuezClaude(registro_costos, tarifa, modelo, prompt, lote_id, api_key, http_client)`: `httpx` directo contra `POST /v1/messages`, `max_tokens` entero, `tool_choice` forzado con `input_schema {probabilidad: number, razon: string}`, temperatura 0. Escribe las 2 filas de costo con `usage` **antes** de validar la salida; después valida y, si no cumple, lanza `SalidaJuezInvalida`.
- `determinista_si_se_demuestra` vive en **un solo lugar**: es atributo de clase del juez (`False` en `JuezClaude` y en `JuezFalso`). El runner lo lee del juez que devuelve `fabrica_juez(nombre_eval, lote_id)`, nunca del `CATALOGO`: el catálogo existe recién en T018 y los tests del runner son de la Fase 2. El test de k=1 usa una subclase de `JuezFalso` con el atributo en `True`.

### Lo que ya costó con Jev (CLAUDE.md), aplicado desde hoy
- **Un caso por llamada.** El runner nunca manda un array de casos al juez ni pide "el ítem 3". Cada `juzgar` recibe un solo caso como objeto con clave; la respuesta es de ese caso.
- **Todo por clave, nada por posición:** `evals.yaml` es un mapa `nombre_eval → config`; `baseline.json` es un mapa `nombre_eval → {…}`; el reporte identifica fallidos por `id`, no por índice. Cuando la 006 enchufe `jev`, la forma ya sirve.
- La versión de Jev queda pineada en `jev-1.13.0` (`config/tarifas.yaml` y `config/fuentes.yaml`). Cuando la 006 agregue `juez: jev`, su `modelo: jev-1.13.0` entra en el fingerprint: cambiar de versión deja el baseline obsoleto, como debe.

### Runner (`run.py`)
- `main(argv, entorno, fabrica_juez=None, registro_costos=None) -> int`. Los tests inyectan juez y registro falsos. Solo en la rama por defecto (`fabrica_juez is None`) `run.py` importa `evals.jueces` y arma los reales (D2, D3). El entorno se lee del mapeo inyectado (default `os.environ`), nunca se imprime.
- Orden, tal cual la spec (Flujo principal §3): validar entorno, `evals.yaml` y datasets (si falla, sale **2** sin llamar a `fabrica_juez`) → fingerprint por eval → `fabrica_juez` por eval → regla de k (usa el baseline del mismo fingerprint; si falla, **2** sin ningún `juzgar`) → por caso: forma primero, juez k veces solo si la forma pasa → PASS^k → `agregado`, `determinacion`, `fallidos` → comparar con baseline → reporte JSON por stdout → código 0/1/2.
- `--config <ruta a evals.yaml>` (default `backend/evals/evals.yaml`); `casos`, `prompt` y `baseline.json` se resuelven relativos a su carpeta. Lo agregó T010 para correr el runner en `tmp_path`; la spec no fijaba cómo se ubica `evals.yaml`.
- `lote_id` = un `uuid4` por corrida, el mismo para todas las filas de costo, y va en el reporte (como texto). A `fabrica_juez` llega como `UUID`, no `str`: `OperacionCosto.lote_id` es `UUID | None` (lo fija `test_lote_id_es_un_uuid_por_corrida`).
- `fabrica_juez(nombre_eval, lote_id) -> Juez` (decisión T011, la revisa el advisor): el argumento es el **nombre del eval**, no la clave `juez`, porque la fábrica por defecto necesita también `modelo` y `prompt` de ese eval. Se llama una vez por eval, después de validar entorno, `evals.yaml` y datasets, y antes de cualquier `juzgar`. El `lote_id` llega al juez por constructor: `JuezClaude(registro_costos, tarifa, modelo, prompt, lote_id, http_client)`.
- La regla de k se valida **después** de `fabrica_juez` (necesita `determinista_si_se_demuestra` del juez devuelto) y **antes** de cualquier `juzgar`: k inválido sale 2 con 0 llamadas.
- Qué recibe el juez: `tarea` = nombre del eval; `caso` = el caso **sin** `etiqueta`/`pertinente` (el juez no ve la respuesta), y en `encaje_icp` con el ICP del dataset bajo la clave `icp`. Una `etiqueta`/`pertinente` ausente o nula es `ConfigInvalida` → 2.
- Comparaciones con baseline y tolerancia redondeadas (p. ej. `round(x, 9)`), para que la suma de errores de float no cambie un "ok" por "regresion".
- Fórmulas (las revisa el advisor):
  - `agregado = casos_que_pasan / todos_los_casos`;
  - `determinacion = juzgados_con_k_resultados_iguales / juzgados`, `null` si `juzgados == 0`;
  - "pasa la corrida i" = (`probabilidad_i ≥ corte`) == (`etiqueta` positiva).
- k=1 solo si el juez que devuelve `fabrica_juez` tiene `determinista_si_se_demuestra` **y** el baseline vigente, con el mismo fingerprint, es de k=3 con `determinacion == 1.0`. Si no, `ConfigInvalida` → 2. `--actualizar-baseline` con k < 3 → 2.

### Fingerprint (`fingerprint.py`)
`sha256` sobre el JSON canónico (`sort_keys=True`) de: bytes del archivo de casos, bytes del prompt, `modelo`, `corte`, `umbral`. Sin `k` ni `tolerancia`.

### Esquema y whitelist (`esquema.py`)
Una whitelist de claves por archivo (`dataset.json`, `casos/calibracion_mensajes.json`, `baseline.json`), las dos regex (email; teléfono = 7+ dígitos con separadores opcionales) aplicadas a strings **y** a números, exentos cerrados (`id`, `fingerprint`, y `as_of`/`fecha` solo si parsean como ISO 8601), enum `rango_ingresos` y sus cortes en COP. La lista exacta de claves la revisa el advisor (T005).

### Reporte (stdout, JSON)
`{"lote_id", "evals": {"<nombre>": {"agregado", "determinacion", "k", "n", "fingerprint", "umbral", "baseline", "estado", "fallidos": [{"id", "motivo"}]}}, "mejora_sin_fijar": [...]}`. `estado` ∈ `ok`, `bajo_umbral`, `regresion`, `sin_baseline`, `baseline_obsoleto`. Motivos de caso: `forma:<regla>`, `juez_salida_invalida` y `fallo_corrida`. `estado` y `fallo_corrida` quedan fijados en la spec (Flujo principal, paso 3, y el test de fingerprint).

### Estructura

```text
backend/
├── pyproject.toml                  # + pyyaml (dependencies), sin anthropic (T017); contrato forbidden app ↛ evals (root_packages lo decide el canario de T002)
├── evals/
│   ├── run.py                      # reemplaza el placeholder
│   ├── config.py · fingerprint.py · esquema.py · exportar_candidatos.py
│   ├── scorers/forma.py
│   ├── jueces/{__init__.py (vacío), puerto.py, catalogo.py, claude.py, falso.py, encaje_v1.md, mensaje_v1.md}
│   ├── dataset.json · casos/calibracion_mensajes.json · baseline.json · evals.yaml · LICENCIA.md
└── tests/
    ├── unit/evals/{test_dataset.py, test_scorers_forma.py, test_juez_claude.py, test_runner.py, test_exportar_candidatos.py}
    ├── contratos/test_juez.py
    ├── anthropic_falso.py                                                   # Messages API falsa (T014–T016)
    ├── arquitectura/{test_import_linter.py, test_costos_por_adaptador.py}   # al primero se le suma un test; el segundo no existía en main y lo crea T013
    └── integration/test_costos_repo.py                                      # se le suma un test
.gitignore                          # + backend/evals/dataset.candidatos.json
docs/{arquitectura-backend.md, decisiones.md}
```

**Gotcha de pytest:** `tests/unit/evals/` va **sin** `__init__.py`. Con uno, pytest lo importa como paquete `evals` y tapa al `backend/evals/` real.

**Structure Decision**: la de la spec (Decisiones técnicas, "Ubicación"). Lo único que suma el plan es `jueces/catalogo.py` (catálogo; `jueces/__init__.py` queda vacío) y `tests/anthropic_falso.py` (fixture compartida).

## Orden de tareas (TDD)

El de la spec, partido por dependencias (detalle en `tasks.md`):
1. **Sin dependencias (Fase 2):** contrato `app` ↛ `evals` → esquema/whitelist (advisor) → scorers de forma → puerto + `JuezFalso` + runner (advisor).
2. **Con D1–D5 (US1):** tests de `JuezClaude`, contrato, arquitectura e integración en rojo (advisor de costos) → `JuezClaude` → composición real → exportación → etiquetado humano (D6) → primera corrida y baseline de `encaje_icp`.
3. **US2, cortable:** calibración sintética + etiquetado + `mensaje_v1.md` + baseline de `juez_mensaje_calibracion`. Si no entra, pasa a la 007 con `test_calibracion_valida`.
4. **Cierre:** docs, decisiones, job `evals` de CI (Q1), merge de `main` tras la 002 (Q5).

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| El job `evals` de CI no corre la corrida real (IX dice "CI invoca ese mismo comando") | Decisión Q1: el job sigue como required check y corre los tests del harness con el juez falso, sin API key; opcionalmente, un chequeo offline de que el fingerprint de `baseline.json` coincide con los archivos actuales. La corrida real necesita `ANTHROPIC_API_KEY`, una base con `costos` y un tenant, y gasta | Poner la API key y una base en CI ahora: más secrets y gasto por push para un chequeo que este fin de semana es local + baseline commiteado (PRD §6b) |
| Juez fuera de `config/fuentes.yaml` | Es tooling: nunca corre en el pipeline de leads. Igual tiene puerto, contrato y `RegistroCostos` (spec) | Registrarlo como `clasificadores.*`: mezclaría producto con medición |
| `JuezFalso` exento de `RegistroCostos` | No sale a la red; exclusión cerrada y nombrada en el test | Darle un registro que nunca escribe: test de arquitectura que nace verde |

## Decisiones del dueño (Q1–Q5, a recomendación del advisor)

1. **Job `evals` de CI:** sigue como required check y corre los tests del harness con el juez falso, sin API key. Opcional: chequeo offline de que el fingerprint de `baseline.json` coincide con los archivos actuales. La desviación del principio IX está en Complexity Tracking.
2. **Sin SDK `anthropic`** (T017, decisión del dueño): el juez usa `httpx` directo con `api_key` por constructor; el SDK se sacó del grupo `dev` y del `uv.lock`. Si la 007 lo quiere para el redactor, lo agrega ahí. `pyyaml` va en `dependencies`, no en dev.
3. **Archivo de casos por eval:** clave `casos: <ruta>` en `evals.yaml` (enmendado en la spec).
4. **`docs/arquitectura-backend.md`:** la 004 lo crea solo con la sección de evals; la 013 lo consolida.
5. **Orden de merge con la 002** (D7): primero se mergea la 002. Después la 004 hace `git merge main` (no rebase), resuelve `[tool.importlinter]` a mano y corre `uv run lint-imports` antes de commitear el merge. El choque de `pyyaml` en `pyproject.toml`/`uv.lock` se resuelve en ese mismo merge.
