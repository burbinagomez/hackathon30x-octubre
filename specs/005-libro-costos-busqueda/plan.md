# Implementation Plan: 005 — Libro de costos, CPL por fuente y "Nueva búsqueda"

**Branch**: `feature/005-libro-costos-busqueda` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Este plan no rediseña lo que fijan la 002, la 003 y la 011: lo cita por línea. Las referencias son a los planes en sus ramas, todavía no en `main`:
> - **002 plan** = `git show 89d3e59:specs/002-puertos-registro-supersociedades/plan.md`;
> - **003 plan** = `git show f393852:specs/003-osm-dedup/plan.md`;
> - **011 plan** = `git show 6c4bd7d:specs/011-datos-gov-co/plan.md`;
> - **011 spec** = `git show f8f9456:specs/011-datos-gov-co/spec.md`, que es la versión con la D7 aplicada.
>
> Lo que la 005 necesita y ninguna de esas fija va a **Preguntas abiertas**, con la sección exacta y un default propuesto, que no se aplica hasta que lo apruebe el dueño.
>
> Artefactos: como en la 002 y la 011, este slice entrega solo `plan.md` y `tasks.md`. Lo que irían en research, data-model, contracts y quickstart está resumido acá.

## Summary

La 005 entrega:
- las vistas SQL del libro de costos (`security_invoker`), con el fixture de 10 leads calculado a mano;
- `lote_id = busquedas.id`;
- `contar()` en `FuenteDescubrimiento`, con suite de contrato propia;
- `costo_maximo_llamada` en `MetaFuente` y el tope de gasto a valor de lista;
- `gasto_busqueda` en `RegistroCostos`;
- el post-filtro de palabras clave y exclusiones;
- los casos de uso `VistaPrevia` y `EjecutarBusqueda` con tope;
- auth mínima: `usuarios` con RLS, funciones `SECURITY DEFINER`, scrypt y JWT HS256;
- los endpoints HTTP;
- el front con login, "Nueva búsqueda" y tablero, con límites por feature e i18n es/en;
- el E2E local;
- la cola de revisión de dedup, que es recortable.

Además absorbe de la 011, por la D7, seis tests y el verde del tablero de naturales (T049 de la 011).

## Technical Context

- **Language/Version:** Python 3.12; TypeScript 5.7 con React 18.3.
- **Primary Dependencies, back:** FastAPI, SQLAlchemy Core + psycopg 3, httpx y pyyaml, todos de la 002. Nueva: **PyJWT**.
- **Primary Dependencies, front:** react-i18next e i18next como dependencias nuevas. Como devDependencies nuevas: `eslint`, `typescript-eslint`, `eslint-plugin-boundaries`, `eslint-plugin-import`, `eslint-import-resolver-typescript` y `eslint-plugin-i18next`. MSW 2.6.6 ya está en `package.json`.
- **Storage:** Postgres (`postgres:16` en CI) y una migración a mano. El número se discute en la pregunta P5.
- **Testing:** pytest, con integración contra Postgres real como `app_rt`. Vitest + Testing Library + MSW en el front y Playwright para el E2E local. Se usan `httpx.MockTransport` y un reloj inyectable, como en la 002 y la 003.
- **Constraints:**
  - ≤ 5 h, con el mínimo de demo declarado en la spec;
  - Croma da ~100 requests en 24 h y 1.500 créditos al mes: hay una sola corrida real, avisada (Fase 12);
  - el pooler va en modo transacción: ningún HTTP corre dentro de una transacción abierta (002 plan:286 y OQ1).
- **Scale/Scope:** 2 módulos nuevos (`tablero`, `acceso`), 9 vistas, 1 tabla, 2 funciones, ~11 endpoints y 4 features de front.

## Constitution Check

| Principio | Qué entrega | Estado |
|---|---|---|
| I Hexagonal | `contar` y `costo_maximo_llamada` entran al puerto con contrato parametrizado sobre el catálogo. `tablero` y `acceso` respetan el `layers` de import-linter (002). En el front, `eslint-plugin-boundaries` con canario (`limites.test.ts`). | ✅ |
| II Test primero | Cada test tiene una mutación que lo pone en rojo por aserción (ver `tasks.md`). Los esqueletos van antes del rojo, para que no haya `ImportError` ni `AttributeError`. El advisor y security revisan antes de aceptar. | ✅ |
| III Tenant/RLS | Vistas `security_invoker` con `test_rls[vista]` y control positivo. `usuarios` con RLS y sin privilegios para `app_rt`. Las funciones `SECURITY DEFINER` llevan `search_path` y `REVOKE` a `PUBLIC`/`anon`/`authenticated`. `pg_views` entra en `test_privilegios_supabase`. | ✅ |
| IV Migraciones | Una migración a mano. `app/modelos.py` suma columnas y `usuarios`, y el drift sigue vacío (las vistas no las compara `compare_metadata`; T006 lo confirma). | ✅ |
| V Seguridad | `SESSION_SECRET` (≥ 32 bytes), `WEB_ORIGIN` y `CROMA_BASE_URL` por `Settings`. Docs desactivadas, CORS cerrado, clave fuera de logs y `extra='forbid'`. | ✅ |
| VI Contacto | El formulario no pide contacto y la cola no lo expone (`test_cola_no_expone_contacto`). El email del usuario es dato de login, no de lead (ver P13). | ⚠️ |
| VII Cumplimiento | Una empresa filtrada por palabra clave no genera lead ni `cumplimiento`. Fusionar no toca `cumplimiento`. `v_atribuciones` sale de `lead_fuentes`. | ✅ |
| VIII Costos | `contar` registra antes de devolver o de lanzar, igual que `buscar`. Todo descubrimiento lleva `lote_id = busqueda.id`. El CPL sale solo de vistas sobre `costos`. | ✅ |
| IX Evals | N/A (sin IA). `fuente='evals'` aparte, en `v_costo_evals`. | — |
| X Doc viva | `docs/arquitectura-backend.md` y `-frontend.md`, más la corrección de PRD §4, en la Fase 13. | ✅ |

## Lo que se usa sin redefinir

| Qué | Dónde está fijado |
|---|---|
| `CriteriosICP.filtros` | 002 plan:58 |
| `PaginaEmpresas.total` ("lo usa la vista previa del 005") | 002 plan:77; `truncado` y `descartados_sin_nombre` en 003 plan:62 |
| `MetaFuente`, armada desde el YAML | 002 plan:80-89; `cuenta_naturales` con default `False` en 011 plan D2 (6c4bd7d:74) |
| `FuenteDescubrimiento` con `meta` como atributo + `buscar` | 002 plan:91-93; D1 de la 011 |
| `CriterioNoSoportado`, `LimiteFuenteAgotado`, `FuenteNoDisponible` | 002 plan:97-99 |
| `RepositorioLeads` | 002 plan:108-115; métodos de dedup en 003 plan:64 |
| `OperacionCosto`, `RegistroCostos` (`registrar`, `requests_24h`, `creditos_mes`) | 002 plan:122-138; módulo `costos` en 002 plan:297 |
| Raíz de composición, tarifas `Decimal(str(v))`, adaptadores por búsqueda con `lote_id` | 002 plan:150 y :286 |
| `costos.ts` lo pone la base | 002 plan:209 y :291 |
| `costos.tipo` cerrado (ya trae `croma_consulta`, `overpass_query` y `socrata_descarga`) | 002 plan:210; la 005 no lo toca |
| `fuente_cache` global, no expuesta | 002 plan:201 |
| `seleccionar_fuentes` → `(seleccionadas, ignoradas)` | 003 plan:65; motivos en 003 spec:41-45 |
| `EjecutarBusqueda` captura errores por fuente | 002 plan:295, 003 plan:55 |
| Costo por intento de `overpass_query`, espera no cobrada, timeout de cliente de 30 s | 003 plan:40, 003 spec:211 y :299 |
| Fórmula de `costo_maximo_llamada` de datos.gov.co | 011 spec (f8f9456):230 |
| Discriminador de caché de datos.gov.co (`tipo: filas\|naturales`, sin `contar`) | 011 (advisor de la 011); la 005 suma `contar` |
| `busquedas.naturales_por_fuente` | 011 spec (f8f9456):37 y :203 |

## Cambios de puerto (son enmienda: la spec 005 es la spec que pide 002 plan:103)

```python
# descubrimiento/dominio — solo se agrega
class FuenteDescubrimiento(Protocol):
    meta: MetaFuente
    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas: ...   # sin cambios
    def contar(self, criterios: CriteriosICP) -> int | None: ...                      # nuevo

@dataclass(frozen=True)
class MetaFuente:                     # 002 plan:80, + un campo con default
    ...
    costo_maximo_llamada: Decimal = Decimal("0")   # origen: ver P4

# costos/dominio
class RegistroCostos(Protocol):
    ...
    def gasto_busqueda(self, busqueda_id: UUID) -> Decimal: ...   # Σ unidades × costo_unitario, gratis incluido (P3)
```

`contar` tiene el mismo contrato que `buscar`:
- valida contra `meta.filtros` antes de hacer cualquier request;
- deja una fila en `costos` por intento, antes de devolver o de lanzar;
- lanza los mismos errores.

`None` significa que la fuente no da conteo, con `motivo='sin_conteo'`.

## Diseño por área (resumen de la spec, con lo que agrega el plan)

**Vistas** (spec:313-335):
- Las 9 vistas van en un archivo de migración, en este orden de dependencia: `v_costos` → `v_costo_evals`, `v_leads_icp` → `v_prorrateo` → `v_desperdicio`, `v_costo_por_lead` → `v_costo_por_canal` → `v_tablero_fuentes` → `v_atribuciones`.
- Todas llevan `WITH (security_invoker = true)` y `GRANT SELECT … TO app_rt`.
- Ninguna redondea.
- Los tests comparan `Decimal` con `Decimal` construido desde string y además asertan `type(v) is Decimal`. Así un cast a `float8` da rojo aunque el valor coincida (`2.0 == Decimal(2)` es `True`). Los esperados del fixture no son enteros (0.3375, 0.2375, 0.282…), y eso cierra la misma puerta por segunda vía.

**`costo_maximo_llamada` por adaptador** (spec:350-353):
- **cs:** 1 crédito × `usd_por_credito`;
- **OSM:** 2 × 30 s × `computo_seg_usd`;
- **`datos_gov_co_rues`:** 2 requests × 2 intentos × 30 s × `computo_seg_usd`, según la 011 spec (f8f9456):230.

Cada uno tiene su test en el archivo del adaptador, y `test_costo_maximo_suma_costo_maximo_llamada_de_cada_fuente` lleva un caso con las tres fuentes.

**Caché de `contar` en datos.gov.co:** la 011 deja su discriminador en `tipo: filas|naturales`, y la 005 suma `tipo: contar`. La segunda llamada con los mismos criterios no hace request ni escribe costo (`test_contar_segunda_llamada_sale_del_cache`). En cs no hace falta un discriminador: `contar` y `buscar(1)` comparten clave a propósito (P12).

**Lote = búsqueda:** `VistaPrevia` crea el borrador **antes** de construir los adaptadores y los arma con `lote_id = borrador.id` (002 plan:286). `EjecutarBusqueda` los vuelve a armar con el mismo id.

**Tope:** el chequeo es `gasto_busqueda(id) + meta.costo_maximo_llamada ≤ tope` antes de cada `buscar`. Lo hace el caso de uso, no el adaptador: el adaptador no conoce el tope.

**Auth:** spec:363-380, sin cambios. `tenant_actual` abre la unidad de trabajo de la 002 con `set_config('app.tenant_id', …, true)`.

**Tablero:**
- `repositorio_tablero.py` solo lee vistas. Suma la columna de naturales de la 011 desde `busquedas.naturales_por_fuente` (P6), y la combina en la API con `meta.cuenta_naturales` del registro.
- La cobertura por país sale del registro, no de la base.

**Front:** spec:414-474, sin cambios. Hoy el repo tiene `src/setupTests.ts`; la spec pide `src/test/setup.ts` y `servidor.ts`, así que T034 lo mueve.

## Migración

Va un único archivo, `supabase/migrations/NNNN_libro_costos_busqueda.sql` (el número sale de P5), con la tabla de spec:398-410:
- en `busquedas`: `+ costo_estimado_usd`, `+ costo_maximo_usd`, `+ ejecutada_en` y el `CHECK` nuevo de `estado` (P1); también la columna de orden del tablero (P6);
- en `leads`: `+ fusionado_en`;
- en `revision_dedup`: `+ motivo`;
- la tabla `usuarios` con RLS;
- las funciones `usuario_para_login` y `fijar_idioma`;
- los índices `(tenant_id, lote_id)` y `(busqueda_id, fuente)`;
- las 9 vistas;
- un `DO` con el guard de `pg_roles` para los `REVOKE EXECUTE`.

`app/modelos.py` suma las columnas y `usuarios`.

## Validación (quickstart)

```bash
cd backend && uv sync && uv run pytest -q && uv run lint-imports
scripts/migrar_local.sh postgresql://postgres@localhost:5432/postgres
cd frontend && npm ci && npm test && npx playwright test
```

La corrida real (Fase 12) se avisa antes. Se anota el saldo de Croma antes y después, si viene `total` y cuánto tarda la ejecución.

## Project Structure

```text
backend/
├── pyproject.toml                         # + PyJWT
├── config/{tarifas.yaml (+ limites_app.tope_maximo_usd), actividades.yaml (+ nombre_es/nombre_en)}
├── app/
│   ├── config.py                          # + session_secret, web_origin, croma_base_url
│   ├── main.py                            # docs off, CORS, routers
│   ├── modelos.py
│   ├── api/{sesion.py, auth.py, busquedas.py, tablero.py, dedup.py, actividades.py, usuarios.py}
│   └── modulos/
│       ├── costos/{dominio/puertos.py (+gasto_busqueda), infraestructura/postgres_costos.py}
│       ├── descubrimiento/
│       │   ├── dominio/{modelos.py (+costo_maximo_llamada), puertos.py (+contar), palabras_clave.py}
│       │   ├── aplicacion/{vista_previa.py, ejecutar_busqueda.py (+tope), resolver_revision.py}
│       │   └── infraestructura/adaptadores/{croma_supersociedades.py, osm_overpass.py, datos_gov_co_rues.py}
│       ├── tablero/infraestructura/persistencia/repositorio_tablero.py
│       └── acceso/{dominio/claves.py, infraestructura/persistencia/repositorio_usuarios.py}
├── scripts/crear_usuario.py
└── tests/
    ├── contratos/test_fuente_descubrimiento.py      # + 3 de contar
    ├── unit/descubrimiento/{test_croma_supersociedades, test_osm_overpass, test_datos_gov_co,
    │                        test_seleccion_fuentes, test_palabras_clave, test_vista_previa, test_ejecutar_con_tope}.py
    ├── integration/{test_vistas_costos, test_rls, test_privilegios_supabase, test_usuarios_repo,
    │                test_costos_repo, test_auth, test_api_busquedas, test_revision_dedup}.py
    └── stubs/servidor_fuentes.py
supabase/migrations/NNNN_libro_costos_busqueda.sql
frontend/
├── eslint.config.js
├── vitest.config.ts
├── src/{App.tsx, main.tsx, api/cliente.ts, i18n/{index.ts, es.json, en.json, elegirIdioma.ts},
│        compartido/{SelectorIdioma.tsx, formato.ts}, test/{setup.ts, servidor.ts},
│        acceso/, busqueda/, tablero/, dedup/}
├── tests/arquitectura/{limites.test.ts, i18n.test.ts}
└── e2e/busqueda.spec.ts
docs/{arquitectura-backend.md, arquitectura-frontend.md, prd.md (§4)}
```

## Preguntas abiertas

Ninguna se resuelve en este plan. Cada fila dice qué tareas bloquea.

| # | Pregunta (sección exacta) | Bloquea | Default propuesto |
|---|---|---|---|
| P1 | **Estados de `busquedas`.** La 002 fija `CHECK IN ('creada','terminada','con_errores')` (002 plan:208, OQ11 :295). La 005 pide `borrador`/`ejecutando`/`completada`/`tope_alcanzado`/`error` (spec:355). La 011 deja "completada" a la 005 (011 plan D6, 6c4bd7d:78). Falta definir qué estado deja la CLI y qué es `error` frente a `con_errores` cuando falla una sola fuente. | T008, T024–T027, T032 | El `CHECK` nuevo es la unión de los 8 valores. La CLI sigue igual. En la API, una fuente caída con otra que respondió deja `completada` con el error por fuente en la respuesta, y `error` queda solo para cuando todas fallan. |
| P2 | **`RepositorioLeads` no crea borradores.** `crear_busqueda(criterios)` (002 plan:109) no recibe canal, tope, mensaje ni costos estimados, y no hay transición `borrador → ejecutando`. | T024–T027 | Se agregan `crear_borrador(criterios, canal, tope, mensaje) -> UUID`, `fijar_estimados(id, estimado, maximo)`, `obtener_borrador(id)` y `pasar_a_ejecutando(id) -> bool` (`UPDATE … WHERE estado='borrador'`). Los métodos del 002 no cambian. |
| P3 | **`gasto_busqueda` en el Protocol `RegistroCostos`** (002 plan:135-138). Si entra al Protocol, los registros falsos de la 002 y la 003 tienen que implementarlo. | T014–T015, T024 | Entra al Protocol, y el registro falso compartido suma el método en el mismo commit. |
| P4 | **De dónde sale `costo_maximo_llamada`.** `MetaFuente` "se arma desde la entrada de fuentes.yaml, no desde la clase" (002 plan:80), pero el valor depende de la tarifa (`computo_seg_usd`, `usd_por_credito`) y de constantes del adaptador (timeout, intentos). La 011 lo deja a la 005 (011 plan D2, 6c4bd7d:74), y la fórmula de datos.gov.co está en la 011 spec (f8f9456):230. | T016–T020 | La fábrica de cada adaptador, en `adaptadores/__init__.py`, lo calcula con la tarifa ya resuelta y hace `dataclasses.replace(meta, costo_maximo_llamada=…)`. El YAML no lo declara. |
| P5 | **Número de migración.** La spec dice `0004` (spec:398), y la 011 dice "el siguiente libre… previsiblemente `0004`" (011 plan D8, 6c4bd7d:80). Con el orden 002 → 003 → 011 → 004 → 005, la 011 toma el `0004` antes. | T001, T005 | El siguiente libre en `main` al pasar la puerta T001 (previsiblemente `0005`). Se corrige `spec.md`. |
| P6 | **Orden del tablero de naturales.** La 011 usa `ORDER BY creada_en DESC` (011 spec f8f9456:203), pero `busquedas` no tiene `creada_en` (002 spec:150). | T031–T032 | La migración de la 005 suma `creada_en timestamptz NOT NULL DEFAULT now()`. Alternativa: ordenar por `ejecutada_en`, que la 005 ya agrega. |
| P7 | **`ignorados` por fuente.** `seleccionar_fuentes` devuelve `(seleccionadas: dict[clave, CriteriosICP], ignoradas: dict[clave, motivo])` (003 plan:65), y la vista previa necesita también los criterios ignorados de cada fuente seleccionada (spec:55). | T021, T025 | Se derivan en `VistaPrevia` como `set(criterios.filtros) - set(seleccionadas[k].filtros)`, sin tocar la firma de la 003. |
| P8 | **Nombre del archivo de selección.** La spec dice `test_seleccion.py` (spec:158) y la 003 crea `test_seleccion_fuentes.py` (003 plan:132). | T021 | Va en `test_seleccion_fuentes.py`, y se corrige `spec.md`. |
| P9 | **`test_tamano_es_refinamiento_no_requisito` puede nacer verde.** La 003 ya manda a `ignorados` los criterios que la fuente no declara (003 spec:45). | T021 | Se acepta como test de caracterización solo si la mutación (tratar `ingresos_min` como requisito) lo pone en rojo, y el advisor lo confirma. |
| P10 | **`EXCLUIDOS`** (002 spec:66, enmendado en 002 plan:297). La 005 suma `repositorio_tablero.py` y `repositorio_usuarios.py` (spec:305). | T033 | Se enmienda en el mismo commit que los crea. |
| P11 | **`limites_app` en `tarifas.yaml`.** Hoy no existe. ¿Lo lee el cargador de tarifas de la 002 o uno aparte? | T032 | Lo lee el mismo cargador, como `Decimal(str(v))`, y llega a la API por `Settings` en la raíz de composición. |
| P12 | **Costo de `contar` de Croma.** Si la página 1 queda en caché, `buscar` no vuelve a cobrar. ¿La fila `croma_consulta` de `contar` es la misma que la de `buscar` (1 crédito en total)? | T017 | Sí: `contar` hace la request y escribe la fila, y `buscar(1)` es cache hit y no escribe nada. Es lo que prueba `test_contar_y_buscar_hacen_una_sola_request`. |
| P13 | **Email de `usuarios` sin cifrar.** El principio VI cubre "correos". El email del usuario tiene que poder buscarse con `lower(email)` para el login. | T012–T013 | Se guarda en claro, como dato de cuenta del operador y no de lead, y se suma a la lista cerrada de `test_ninguna_columna_de_contacto_fuera_del_catalogo` (003) con esa razón. Lo revisa security. |
| P14 | **Costo de `contar` de OSM en la vista previa de un ICP de BR o PE** (estimado de OSM como cota baja, spec:341). Sin pregunta de diseño, pero se registra para la Fase 12. | — | Se mide en la corrida real. |

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| Un campo de `MetaFuente` que no sale del YAML (P4) | Depende de la tarifa y del timeout del adaptador, y duplicarlo en el YAML los desincroniza | Declararlo en `fuentes.yaml`: un cambio de tarifa no lo movería |
| Módulo `tablero` sin dominio | La lógica vive en SQL (PRD §7, spec:300) | Calcular el CPL en Python: tendría dos fuentes de verdad |
| Funciones `SECURITY DEFINER` | El login ocurre antes de conocer el tenant, y `app_rt` no puede leer `usuarios` | Darle `SELECT` a `app_rt`: podría volcar los hashes de todos los tenants |
