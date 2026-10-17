# Tasks: 002 — Puertos, registro de adaptadores y Supersociedades

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Tests**: obligatorios (constitución II). Cada **Rojo** se corre y se ve fallar por la razón esperada antes de su **Verde**. Un test que nace verde se reescribe.
**Revisión**: el `advisor` revisa los tests marcados *(advisor)* antes de escribir su Verde.

Formato: `- [ ] T0NN [P] [US1] Rojo/Verde: qué, en qué archivo`. `[P]` = archivo distinto y sin dependencia de una tarea abierta. Rutas relativas a la raíz del repo.

La spec tiene una sola historia (US1: una búsqueda por CLI deja leads deduplicados con su costo y su cumplimiento). Las fases siguen los pasos 1 a 9 de la spec.

## Fase 1: Setup

- [ ] T001 Pasar `httpx` de dev a runtime y sumar `pyyaml` en `backend/pyproject.toml`; `uv lock` actualiza `backend/uv.lock`.
- [ ] T002 [P] Agregar `croma_api_key: SecretStr | None = None` a `Settings` en `backend/app/config.py` (sin default con valor; nunca en logs).
- [ ] T003 [P] Crear el esqueleto vacío `backend/app/modulos/descubrimiento/{dominio,aplicacion,infraestructura/adaptadores,infraestructura/persistencia}/__init__.py` y `backend/tests/{contratos,unit/descubrimiento}/__init__.py` si hace falta.

## Fase 2: Fundacional (bloquea a US1)

### Paso 1: canario de capas

- [ ] T004 Rojo: `backend/tests/arquitectura/test_import_linter.py::test_detecta_violacion_de_capas`. Copia `pyproject.toml` a `tmp_path`, escribe un `dominio/x.py` que importa `infraestructura`, corre `lint-imports` y espera `"Capas de descubrimiento BROKEN"`. Rojo: el contrato no existe.
- [ ] T005 Verde: contrato `layers` "Capas de descubrimiento" (`infraestructura > aplicacion > dominio`, containers `app.modulos.descubrimiento`) en `backend/pyproject.toml`. `uv run lint-imports` verde sobre el repo real.

### Paso 2: dominio y registro

- [ ] T006 [P] Rojo: tests de dominio en `backend/tests/unit/descubrimiento/test_dominio.py`: `normalizar_nit("900.123.456-7") == "900123456"`, `normalizar_nit("900123456") == "900123456"` (sin guion no se corta, pregunta abierta 8), `cubre(meta, criterios)` por país, por `"*"` y por filtros fuera de `meta.filtros`.
- [ ] T007 Verde: `EmpresaCruda`, `Actividad`, `CriteriosICP`, `PaginaEmpresas`, `MetaFuente`, `OperacionCosto` en `backend/app/modulos/descubrimiento/dominio/modelos.py`; `normalizar_nit` y `cubre` en `dominio/nit.py` y `dominio/modelos.py`; `CriterioNoSoportado`, `LimiteFuenteAgotado`, `FuenteNoDisponible`, `RegistroInvalido` en `dominio/errores.py`; Protocols `FuenteDescubrimiento`, `RegistroCostos`, `RepositorioLeads` en `dominio/puertos.py`. Firmas exactas: plan.md, sección Puerto.
- [ ] T008 [P] Rojo: `backend/tests/unit/descubrimiento/test_registro.py` con los 4 tests de la spec: habilitada en catálogo → `fuentes`; habilitada sin implementación → `sin_implementacion` (`{"croma_dian_trade_co", "osm_overpass"}` contra el YAML real); clave del catálogo ausente del YAML → `RegistroInvalido`; habilitada sin `paises`/`filtros` → `RegistroInvalido` (deshabilitada incompleta no rompe). YAML de prueba en `tmp_path`.
- [ ] T009 Verde: `cargar_registro(ruta_yaml, catalogo) -> Registro` en `backend/app/modulos/descubrimiento/aplicacion/registro.py`. Lee solo `fuentes_descubrimiento`, con `yaml.safe_load`.

### Paso 3: migración 0002, persistencia y siembra

- [ ] T010 Rojo: en `backend/tests/arquitectura/test_migraciones.py`, reemplazar `assert _aplicadas(base_vacia) == "0001"` por la comparación contra las versiones de `supabase/migrations/*.sql`. Rojo: falta `0002`.
- [ ] T011 [P] Rojo *(advisor)*: `backend/tests/integration/test_rls.py::test_rls[tabla]` parametrizado sobre `tenants, busquedas, leads, lead_fuentes, cumplimiento, costos`: con tenant A no se ve ni se inserta lo de B. Más `test_tenant_no_sobrevive_al_commit`. `fuente_cache` fuera del parámetro, con un test que confirma que no tiene RLS ni `tenant_id`.
- [ ] T012 [P] Rojo *(advisor)*: `backend/tests/integration/test_privilegios_supabase.py`, los 3 tests de la spec: `anon` y `authenticated` sin privilegios sobre ninguna tabla de `public`, y la migración no falla si esos roles no existen.
- [ ] T013 [P] Crear `backend/scripts/supabase_simulado.sql` (crea `anon` y `authenticated` con los `GRANT` por defecto de Supabase) y sumarlo en `.github/workflows/ci.yml` entre `roles.sql` y `scripts/migrar_local.sh`.
- [ ] T014 Verde: `supabase/migrations/0002_descubrimiento.sql` a mano: `tenants`, `busquedas`, `leads` (`UNIQUE (tenant_id, pais, id_fiscal)`, `tipo_titular` NOT NULL default `desconocido`, `idioma_contacto` GENERATED desde `pais`), `lead_fuentes` (`UNIQUE (lead_id, fuente, busqueda_id)`), `cumplimiento` (`lead_id` UNIQUE, `base_legal` nullable), `costos` (`gratis` NOT NULL, `ts` default `now()`, índice `(tenant_id, proveedor, ts)`), `fuente_cache` (UNIQUE `(proveedor, endpoint, hash_params)`, sin RLS). RLS `USING/WITH CHECK` por `app.tenant_id`; `GRANT` y bloque `DO` de `REVOKE` según plan.md, sección Datos.
- [ ] T015 Verde: declarar las 7 tablas en `backend/app/modelos.py` (Core, `Computed(..., persisted=True)` para `idioma_contacto`) hasta que `test_migrar_local_desde_vacio_dos_veces_sin_drift` dé verde. T010, T011 y T012 en verde.
- [ ] T016 Verde: unidad de trabajo por tenant en `backend/app/db.py` (`set_config('app.tenant_id', :id, true)` como primera sentencia de la transacción).
- [ ] T017 [P] Rojo *(advisor)*: `backend/tests/integration/test_leads_repo.py`, los 3 tests de la spec (lead nuevo crea `cumplimiento` en la misma transacción; `(pais, id_fiscal)` repetido reusa el lead; `lead_fuentes` repetido no duplica).
- [ ] T018 Verde: `backend/app/modulos/descubrimiento/infraestructura/persistencia/repositorio_leads.py`, implementación de `RepositorioLeads` con `ON CONFLICT`.
- [ ] T019 [P] Rojo: `backend/tests/integration/test_sembrar_tenant.py`, los 2 tests de la spec (upsert idempotente por nombre; pide la URL por `getpass` y no la imprime).
- [ ] T020 Verde: `backend/scripts/sembrar_tenant.py`.

### Paso 4: libro de costos en Postgres

- [ ] T021 Rojo *(advisor)*: `backend/tests/integration/test_costos_repo.py`: fila de Croma con `costo_unitario=0.00099`, `gratis=true` y `tenant_id`; `requests_24h` solo cuenta la ventana de 24 h; `creditos_mes` corta en el mes UTC aunque la sesión tenga `SET TIME ZONE 'America/Bogota'`; la fila sobrevive al rollback de la transacción de leads (pregunta abierta 1).
- [ ] T022 Verde: `backend/app/modulos/descubrimiento/infraestructura/persistencia/postgres_costos.py`, con transacción propia por `registrar`.
- [ ] T023 [P] Rojo: test del upsert y la lectura de `fuente_cache` en `backend/tests/integration/test_costos_repo.py::test_cache_*` (misma clave pisa, `as_of` se conserva en la lectura).
- [ ] T024 Verde: `backend/app/modulos/descubrimiento/infraestructura/persistencia/repositorio_cache.py`.

**Checkpoint**: dominio, registro, migración y persistencia en verde. Recién acá arranca US1.

## Fase 3: US1, búsqueda por CLI con Supersociedades

**Objetivo**: `uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11` deja leads deduplicados, con costo y cumplimiento.
**Prueba independiente**: los tests de esta fase, sin red; más una corrida real en T034.

### Paso 5: adaptador Croma

- [ ] T025 [P] [US1] Crear la respuesta sintética `backend/tests/fixtures/croma_supersociedades_sintetica.json` (forma de la respuesta de Croma, datos inventados, sin NIT reales).
- [ ] T026 [US1] Rojo *(advisor)*: `backend/tests/unit/descubrimiento/test_croma_supersociedades.py`, los 8 tests de la spec con `httpx.MockTransport` y un `RegistroCostos` falso: mapeo a `EmpresaCruda` (`actividad == ("4711", "CIIU")`, `tipo_titular == "juridica"`, NIT sin DV); `gratis` en 1.499 y no en 1.500; 100 requests en 24 h → `LimiteFuenteAgotado` y 0 requests; 99 y 990 créditos sí llaman; 502 + 200 → 2 filas (la del 502 con `unidades=0`); hit de caché → 0 filas y 0 requests; criterio no soportado → 0 requests. Rojo: no existe el módulo.
- [ ] T027 [US1] Verde: `backend/app/modulos/descubrimiento/infraestructura/adaptadores/croma_supersociedades.py`, en el orden de plan.md (validar → caché → límite antes de cada intento → request con reintento → fila por intento → upsert caché → mapeo). API key desde el constructor, nunca en el mensaje de un error.
- [ ] T028 [US1] Registrar `{"croma_supersociedades_co": CromaSupersociedades}` en `backend/app/modulos/descubrimiento/infraestructura/adaptadores/__init__.py`. Corre de nuevo T008 contra el catálogo real.

### Paso 6: contrato y adaptadores declarados

- [ ] T029 [P] [US1] Rojo: `backend/tests/contratos/test_fuente_descubrimiento.py` parametrizado sobre `catalogo`, con `test_hay_fabrica_para_cada_clave_del_catalogo` y los 3 tests de la spec (plan.md, sección Suite de contrato). Rojo: falta `backend/tests/contratos/fabricas.py`.
- [ ] T030 [US1] Verde: `backend/tests/contratos/fabricas.py` con la fábrica de `croma_supersociedades_co` (transporte falso + fixture de T025).
- [ ] T031 [P] [US1] Rojo: `backend/tests/arquitectura/test_registro_adaptadores.py` (2 tests: toda clase que implementa `FuenteDescubrimiento` está en el catálogo; toda clave del catálogo está en el YAML; solo chequea puertos que existen, pregunta abierta en la spec) y `backend/tests/arquitectura/test_costos_por_adaptador.py` (todo adaptador del catálogo pide `RegistroCostos` en el constructor). Rojo: se prueba primero con una clase fuera del catálogo en `tmp_path`.
- [ ] T032 [US1] Verde: lo que T031 exija (si nace verde contra el código de T027, el rojo de T031 es el de la clase de prueba).

### Paso 7: caso de uso

- [ ] T033 [US1] Rojo *(advisor)*: `backend/tests/unit/descubrimiento/test_ejecutar_busqueda.py`, los 7 tests de la spec con fuentes y repositorio falsos: elige solo habilitadas e implementadas que cubren país y filtros; ninguna → `sin_fuente_para(pais, criterio)`; dedup por `(pais, id_fiscal)` entre fuentes y contra la base; lead nuevo con `cumplimiento`, existente reusado; `lead_fuentes` siempre; `LimiteFuenteAgotado` y `FuenteNoDisponible` se reportan en el resultado sin tragar (pregunta abierta 11); el resumen trae encontrados, únicos, nuevos, créditos y `sin_implementacion`.
- [ ] T034 [US1] Verde: `backend/app/modulos/descubrimiento/aplicacion/ejecutar_busqueda.py`, sin importar `infraestructura` (lo cuida T005).

### Paso 8: CLI y corrida real

- [ ] T035 [US1] Rojo: `backend/tests/unit/test_cli.py`: `buscar` sin `--tenant` sale con error; con transporte falso inyectado imprime el resumen; la salida no contiene la API key ni la `DATABASE_URL`.
- [ ] T036 [US1] Verde: `backend/app/cli.py`, raíz de composición (lee `fuentes.yaml` y `tarifas.yaml`, arma adaptadores por búsqueda con `lote_id = busqueda_id`, pasa `limites`).
- [ ] T037 [US1] Una corrida real contra Croma, avisada antes (gasta 1 request de 100 y 1 crédito). Confirmar: forma de `departamento` (pregunta 9), NIT con o sin DV (pregunta 8), 4xx (pregunta 5). Una segunda corrida idéntica muestra 0 créditos. Lo que cambie vuelve como Rojo en T026, no como parche.

## Fase 4: Pulido

- [ ] T038 [P] `docs/arquitectura-backend.md`: módulo `descubrimiento`, puerto, registro, suite de contrato y cómo sumar un adaptador (pregunta abierta 12).
- [ ] T039 [P] `.claude/skills/slice-tdd/SKILL.md`: prefijo de rama `slice/` → `feature/`, como pide la spec.
- [ ] T040 Suite completa: `cd backend && uv run pytest -q && uv run lint-imports`, y `scripts/migrar_local.sh` dos veces sobre base vacía.

## Dependencias

- Setup (T001-T003) → Fundacional → US1 → Pulido.
- T004 → T005. T006 → T007 → T008 → T009.
- T010, T011, T012 (+ T013) → T014 → T015 → T016 → T017/T019/T021/T023 → sus Verde.
- T007, T009, T022, T024 → T026 → T027 → T028 → T029-T032.
- T018, T028 → T033 → T034 → T035 → T036 → T037.
- T038-T040 al final.

## Paralelo

- Setup: T002 y T003 juntos.
- Paso 2: T006 y T008 (tests) en paralelo; sus Verde en orden.
- Paso 3: T011, T012 y T013 en paralelo; después de T016, T017, T019, T021 y T023 en paralelo.
- US1: T025 mientras se escribe T026; T029 y T031 en paralelo.
- Pulido: T038 y T039.

## Estrategia

MVP = la fase 3 completa: es el único incremento con valor (una búsqueda real deja leads). No hay entrega parcial útil antes de T036. Si el tiempo no alcanza, se corta T037 (la corrida real) y se anota, nunca un test de RLS, costos o dedup.
