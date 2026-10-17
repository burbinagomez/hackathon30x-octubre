# Tasks: 002 — Puertos, registro de adaptadores y Supersociedades

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Tests**: obligatorios (constitución II). Cada **Rojo** se corre y se ve fallar **por la razón esperada** antes de su **Verde**. `ImportError` o `UndefinedTable` no cuentan como rojo de un test de comportamiento: donde la tabla o el módulo tienen que existir primero, el rojo es por **mutación** (se escribe la versión sin la propiedad, se ve el rojo, se agrega). Un test que nace verde se reescribe.
**Revisión**: el `advisor` revisa los tests marcados *(advisor)* antes de escribir su Verde.

Formato: `- [ ] T0NN [P] [US1] Rojo/Verde: qué, en qué archivo`. `[P]` = archivo distinto y sin dependencia de una tarea abierta. Rutas relativas a la raíz del repo.

La spec tiene una sola historia (US1: una búsqueda por CLI deja leads deduplicados con su costo y su cumplimiento). Las fases siguen los pasos 1 a 9 de la spec.

## Fase 1: Setup

- [ ] T001 Mover `httpx` del grupo dev a `dependencies` y sumar `pyyaml` a `dependencies` en `backend/pyproject.toml`; `uv lock` actualiza `backend/uv.lock`. (La 004 y la 012 declaran la misma línea de `pyyaml`; el choque se resuelve en el merge siguiente.)
- [ ] T002 [P] Agregar `croma_api_key: SecretStr | None = None` a `Settings` en `backend/app/config.py` (nunca en logs).
- [ ] T003 [P] Crear los paquetes vacíos `backend/app/modulos/descubrimiento/{dominio,aplicacion,infraestructura/adaptadores,infraestructura/persistencia}/__init__.py`, `backend/app/modulos/costos/{dominio,infraestructura}/__init__.py` y `backend/tests/{contratos,unit/descubrimiento}/__init__.py` si hace falta.

## Fase 2: Fundacional (bloquea a US1)

### Paso 1: canario de capas

- [ ] T004 Rojo: `backend/tests/arquitectura/test_import_linter.py::test_detecta_violacion_de_capas`. Copia `pyproject.toml` a `tmp_path`, escribe un `descubrimiento/dominio/x.py` que importa `descubrimiento.infraestructura`, corre `lint-imports` y espera código ≠ 0 y el nombre del contrato `layers`. Rojo: el contrato no existe.
- [ ] T005 Verde: contrato `layers` (`infraestructura > aplicacion > dominio`) en `backend/pyproject.toml` con **todos** los containers de `app.modulos.*` (`app.modulos.descubrimiento`, `app.modulos.costos`). Si import-linter exige las tres capas en cada container, `costos/aplicacion/__init__.py` vacío. `uv run lint-imports` verde sobre el repo real.

### Paso 2: dominio y registro

- [ ] T006 [P] Rojo: `backend/tests/unit/descubrimiento/test_dominio.py`: `normalizar_nit("900.123.456-7") == "900123456"`, `normalizar_nit("900123456") == "900123456"`, `normalizar_nit("9001234567") == "9001234567"` (sin guion no se corta el DV, pregunta abierta 8); `cubre(meta, criterios)` por país, por `"*"` y por un filtro fuera de `meta.filtros`.
- [ ] T007 Verde: en `backend/app/modulos/descubrimiento/dominio/`: `modelos.py` (`EmpresaCruda`, `Actividad`, `CriteriosICP`, `PaginaEmpresas`, `MetaFuente`, `cubre`), `nit.py` (`normalizar_nit`), `errores.py` (`CriterioNoSoportado`, `LimiteFuenteAgotado`, `FuenteNoDisponible`, `RegistroInvalido`), `puertos.py` (`FuenteDescubrimiento`, `RepositorioLeads`). En `backend/app/modulos/costos/dominio/`: `OperacionCosto` y `RegistroCostos`. Firmas exactas: plan.md, sección Puerto.
- [ ] T008 [P] Rojo: `backend/tests/unit/descubrimiento/test_registro.py` con los 4 tests de la spec. El primero que se escribe es `test_carga_config_fuentes_yaml_real_sin_error` (YAML real, catálogo real): **queda en rojo hasta T029**, porque el catálogo recién tiene `croma_supersociedades_co` ahí. Los otros 3 usan YAML en `tmp_path` y un catálogo de prueba con una clase falsa, y quedan verdes en T009.
- [ ] T009 Verde: `cargar_registro(ruta_yaml, catalogo) -> Registro` en `backend/app/modulos/descubrimiento/aplicacion/registro.py`. Lee solo `fuentes_descubrimiento`, con `yaml.safe_load`.

### Paso 3: migración 0002, persistencia y siembra

- [ ] T010 [P] Crear `backend/scripts/supabase_simulado.sql` (`anon` y `authenticated` `NOLOGIN` + `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated`) y sumarlo en `.github/workflows/ci.yml` como paso propio después de "roles.sql + password de test" y antes de "supabase/migrations desde vacío". Va primero, para que los tests de privilegios puedan nacer en rojo.
- [ ] T011 `supabase/migrations/0002_descubrimiento.sql`, **primera versión, sin `ENABLE ROW LEVEL SECURITY`/políticas y sin el bloque `DO` de `REVOKE`** (base para los rojos por mutación): `tenants`, `busquedas` (`estado` NOT NULL DEFAULT `'creada'` CHECK `IN ('creada','terminada','con_errores')`), `leads` (`UNIQUE (tenant_id, pais, id_fiscal)`, `tipo_titular` NOT NULL DEFAULT `'desconocido'`, `idioma_contacto` GENERATED desde `pais`), `lead_fuentes` (`UNIQUE (lead_id, fuente, busqueda_id)`), `cumplimiento` (`lead_id` UNIQUE, `base_legal` nullable), `costos` (`gratis bool NOT NULL`, `ts` DEFAULT `now()`, índice `(tenant_id, proveedor, ts)`), `fuente_cache` (UNIQUE `(proveedor, endpoint, hash_params)`). FKs y `GRANT` a `app_rt` según plan.md, sección Datos.
- [ ] T012 Rojo: con la `0002` en el repo, correr `backend/tests/arquitectura/test_migraciones.py::test_migrar_local_desde_vacio_dos_veces_sin_drift` y verlo fallar en `assert _aplicadas(base_vacia) == "0001"`.
- [ ] T013 Verde: reemplazar ese assert por la comparación contra las versiones de `supabase/migrations/*.sql` (ruta `BACKEND.parent / "supabase" / "migrations"`, versión = antes del primer `_`, orden de texto, unidas por coma).
- [ ] T014 Verde: declarar las 7 tablas en `backend/app/modelos.py` (Core) hasta que `compare_metadata` dé vacío: tipos exactos (`UUID`, `JSONB`, `DateTime(timezone=True)`, `Numeric`), `UniqueConstraint` `(tenant_id, pais, id_fiscal)`, `(lead_id, fuente, busqueda_id)`, `cumplimiento.lead_id`, `(proveedor, endpoint, hash_params)`; `Index` `(tenant_id, proveedor, ts)`; todas las `ForeignKey`; `Computed(..., persisted=True)` para `idioma_contacto`. T012 en verde.
- [ ] T015 Rojo *(advisor)*: `backend/tests/integration/test_privilegios_supabase.py::test_tenant_no_sobrevive_al_commit`, con la unidad de trabajo real sobre el engine de `app_rt`. Rojo por mutación: primera versión de la unidad de trabajo en `backend/app/db.py` con `set_config('app.tenant_id', :id, false)` (de sesión) → el tenant sobrevive al commit → rojo.
- [ ] T016 Verde: unidad de trabajo en `backend/app/db.py` con `set_config('app.tenant_id', :id, true)` como primera sentencia de la transacción.
- [ ] T017 [P] Rojo *(advisor)*: `backend/tests/integration/test_rls.py::test_tenant_b_no_accede_a_datos_de_a[tabla]` sobre `tenants, busquedas, leads, lead_fuentes, cumplimiento, costos`, usando la unidad de trabajo de T016. Como tenant B: SELECT vacío; UPDATE y DELETE afectan 0 filas de A; INSERT con el `tenant_id` de A rechazado. En `tenants` el INSERT lo rechaza la falta de privilegio: asertar `InsufficientPrivilege`. `fuente_cache` en la lista de exclusiones con su razón. Rojo por mutación: la `0002` de T011 no tiene RLS → B ve lo de A.
- [ ] T018 [P] Rojo *(advisor)*: en `backend/tests/integration/test_privilegios_supabase.py`, `test_anon_y_authenticated_sin_privilegios[rol-tabla]` (tablas de `pg_tables`, con assert previo de que incluye `leads`) y `test_default_privileges_no_conceden_a_anon_ni_authenticated` (tabla regular `public.x`, no `TEMP`, con rollback). Rojo por mutación: la `0002` de T011 no tiene el bloque `DO` de `REVOKE` y `supabase_simulado.sql` concedió todo. El escenario sin `anon`/`authenticated` lo cubre `base_vacia` de `test_migraciones.py`.
- [ ] T019 Verde: agregar a `supabase/migrations/0002_descubrimiento.sql` el `ENABLE ROW LEVEL SECURITY` + políticas `USING/WITH CHECK` (en `tenants`, `USING (id = …)`) y, al final, el bloque `DO` de `REVOKE` condicionado a `pg_roles`. T017 y T018 en verde; T012 sigue verde.
- [ ] T020 [P] Rojo *(advisor)*: `backend/tests/integration/test_leads_repo.py`:
  - `test_unico_por_tenant_pais_id_fiscal` y `test_unico_lead_fuente_busqueda` (los de la spec);
  - `test_lead_persistido_conserva_tipo_titular`: una `EmpresaCruda` de Supersociedades guardada y releída tiene `tipo_titular == 'juridica'`;
  - `test_lead_nuevo_y_cumplimiento_en_una_transaccion`: forzar un fallo al insertar el `cumplimiento` (monkeypatch del INSERT de cumplimiento para que lance) → 0 filas en `leads`;
  - `test_crear_busqueda_se_confirma_antes`: `crear_busqueda` deja la fila visible desde otra conexión antes de que se llame a ningún adaptador.
- [ ] T021 Verde: `backend/app/modulos/descubrimiento/infraestructura/persistencia/repositorio_leads.py`: `obtener_o_crear_lead(e, licencia)` inserta lead + `cumplimiento` en una transacción cuando es nuevo; `crear_busqueda` y `cerrar_busqueda` en transacción propia; `agregar_lead_fuente` con `ON CONFLICT DO NOTHING`.
- [ ] T022 [P] Rojo: `backend/tests/integration/test_sembrar_tenant.py`, los 2 tests de la spec (upsert por `id` con `nombre` e `idioma` nuevos; `getpass` con monkeypatch, exit ≠ 0, la password no aparece en stdout/stderr).
- [ ] T023 Verde: `backend/scripts/sembrar_tenant.py`.

### Paso 4: libro de costos en Postgres

- [ ] T024 Rojo *(advisor)*: `backend/tests/integration/test_costos_repo.py`, contadores sembrados relativo a `now()` de la DB con `unidades` 0, 1 y 10: `test_requests_24h_cuenta_filas_en_ventana` (23 h 59 min sí, 24 h 01 min no, aunque la de adentro tenga `unidades=0`); `test_creditos_mes_suma_unidades_del_mes_calendario_utc` (con `SET TIME ZONE 'America/Bogota'`); `test_registrar_sobrevive_al_rollback_de_otra_transaccion` (pregunta abierta 1).
- [ ] T025 Verde: `backend/app/modulos/costos/infraestructura/postgres_costos.py`, con transacción propia por `registrar`.
- [ ] T026 [P] Rojo: `backend/tests/integration/test_costos_repo.py::test_cache_*`: misma clave pisa la respuesta; la lectura devuelve `respuesta` y `as_of`.
- [ ] T027 Verde: `backend/app/modulos/descubrimiento/infraestructura/persistencia/repositorio_cache.py`, con transacción propia por upsert.

**Checkpoint**: dominio, registro, migración y persistencia en verde. Recién acá arranca US1.

## Fase 3: US1, búsqueda por CLI con Supersociedades

**Objetivo**: `uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11` deja leads deduplicados, con costo y cumplimiento.
**Prueba independiente**: los tests de esta fase, sin red; más una corrida real en T040.

### Paso 5: adaptador Croma

- [ ] T028 [P] [US1] Crear la respuesta sintética `backend/tests/fixtures/croma_supersociedades_sintetica.json` (forma de la respuesta de Croma, datos inventados, sin NIT reales).
- [ ] T029 [US1] Rojo *(advisor)*: `backend/tests/unit/descubrimiento/test_croma_supersociedades.py` con `httpx.MockTransport` y un `RegistroCostos` falso:
  - `test_mapea_respuesta_a_empresa_cruda` (`900.123.456-7` → `"900123456"`, `juridica`, `("4711", "CIIU")`, ciudad y dirección; `url_origen` sin query ni key);
  - `test_registra_un_credito_por_request`: la fila tiene `tipo="croma_consulta"`, `unidades=1`, `costo_unitario == tarifas.croma.usd_por_credito`, `proveedor="croma"`, `fuente="croma_supersociedades_co"`, `lead_id=None` y el `lote_id` de la corrida;
  - `test_body_enviado_a_croma`: el body trae `ciiu_code="4711"`, `department` (desde `departamento`), `per_page=100`, `page=1`; la API key no está en el body ni en `hash_params`;
  - `test_dentro_del_cupo_mensual_registra_gratis` (1499) y `test_cupo_mensual_agotado_registra_no_gratis` (1500, mismo `costo_unitario`);
  - `test_no_llama_si_se_agoto_el_limite_de_24h` (100 → `LimiteFuenteAgotado`, 0 requests) y `test_limite_de_24h_usa_requests_no_creditos` (99 y 990 → llama);
  - `test_reintento_tras_502_registra_cada_intento` (502 + 200 → 2 requests, 2 filas, la del 502 con `unidades=0` y `costo_unitario=0`);
  - `test_502_con_99_previas_no_reintenta`: con `requests_24h` que pasa de 99 a 100 tras el 502 → 1 request, 1 fila escrita, `LimiteFuenteAgotado`;
  - `test_429_lanza_limite_sin_reintento`: 1 request, 1 fila, `LimiteFuenteAgotado`;
  - `test_respuesta_cacheada_no_gasta_credito`: la primera llamada llena el caché **vía el adaptador** (no sembrado a mano); la segunda idéntica hace 0 requests y 0 filas nuevas;
  - `test_error_no_se_cachea`: tras un 4xx y tras 5xx agotados, el caché sigue vacío y la siguiente llamada sí hace request.
  Rojo: el adaptador no existe; tras el esqueleto vacío de la clase, cada test falla por su aserción.
- [ ] T030 [US1] Verde: `backend/app/modulos/descubrimiento/infraestructura/adaptadores/croma_supersociedades.py`, en el orden de plan.md (validar → body → caché → límite antes de cada intento → request con reintento → fila por intento → caché solo en 200 → mapeo). API key desde el constructor, solo en el header, nunca en el mensaje de un error.
- [ ] T031 [US1] Registrar `{"croma_supersociedades_co": CromaSupersociedades}` en `backend/app/modulos/descubrimiento/infraestructura/adaptadores/__init__.py`. `test_carga_config_fuentes_yaml_real_sin_error` (T008) pasa a verde.
- [ ] T032 [US1] Rojo *(advisor)*: en `backend/tests/integration/test_costos_repo.py`, `test_croma_consulta_escribe_fila_en_costos` (adaptador con transporte falso + `postgres_costos` real: 1 fila con `tipo='croma_consulta'`, `unidades=1`, `costo_unitario=0.00099`, `gratis=true`, `tenant_id` del contexto) y `test_reintento_cuenta_para_el_limite` (98 filas previas, 502 + 200 → `requests_24h == 100`, `creditos_mes` +1, la siguiente búsqueda lanza `LimiteFuenteAgotado`). Rojo por mutación: con `registrar` del adaptador comentado, 0 filas.
- [ ] T033 [US1] Verde: lo que T032 exija en el adaptador o en `postgres_costos`, sin tocar los tests unitarios.

### Paso 6: contrato y adaptadores declarados

- [ ] T034 [P] [US1] Rojo: `backend/tests/contratos/test_fuente_descubrimiento.py` parametrizado sobre `catalogo`, con `assert catalogo` a nivel de módulo, `test_hay_fabrica_para_cada_clave_del_catalogo` y los 3 tests de la spec (plan.md, sección Suite de contrato). Rojo real de `test_registra_costo_antes_de_devolver`: correrlo una vez con una fábrica que devuelve un adaptador falso que no llama a `registrar` → rojo.
- [ ] T035 [US1] Verde: `backend/tests/contratos/fabricas.py` con la fábrica de `croma_supersociedades_co` (transporte falso + fixture de T028).
- [ ] T036 [P] [US1] Rojo: `backend/tests/arquitectura/test_registro_adaptadores.py` (`test_todo_adaptador_de_registro_esta_declarado` y `test_persistencia_solo_contiene_excluidos_y_no_importa_http`, con `EXCLUIDOS` de la spec ya enmendado a `costos/infraestructura/postgres_costos.py`) y `backend/tests/arquitectura/test_costos_por_adaptador.py::test_todo_adaptador_de_registro_recibe_registro_costos`. Los dos recorridos afirman que encontraron **al menos una** clase antes de chequearla. Solo chequean puertos que existen hoy. Rojo: una clase fuera del catálogo / sin `RegistroCostos` / un archivo extra en `persistencia/` en `tmp_path`.
- [ ] T037 [US1] Verde: lo que T036 exija sobre el código real.

### Paso 7: caso de uso

- [ ] T038 [US1] Rojo *(advisor)*: `backend/tests/unit/descubrimiento/test_ejecutar_busqueda.py`, los 7 tests de la spec con fuentes y repositorio falsos, más: el resultado reporta `LimiteFuenteAgotado`/`FuenteNoDisponible` por fuente sin tragarlos y la búsqueda cierra `con_errores` (pregunta 11). La fuente falsa devuelve el NIT **sin** normalizar (`900.123.456-7`), así que la clave de dedup tiene que pasar por `normalizar_nit` en el caso de uso; si no, `test_nit_con_y_sin_formato_es_el_mismo_lead` queda rojo.
- [ ] T039 [US1] Verde: `backend/app/modulos/descubrimiento/aplicacion/ejecutar_busqueda.py` (`crear_busqueda` → adaptadores → `obtener_o_crear_lead` + `agregar_lead_fuente` → `cerrar_busqueda`), sin importar `infraestructura` (lo cuida T005).

### Paso 8: CLI y corrida real

- [ ] T040 [US1] Rojo: `backend/tests/unit/test_cli.py`: `buscar` sin `--tenant` sale con error; con transporte falso inyectado imprime el resumen; la salida no contiene la API key ni la `DATABASE_URL`.
- [ ] T041 [US1] Verde: `backend/app/cli.py`, raíz de composición (lee `fuentes.yaml` y `tarifas.yaml`, arma adaptadores por búsqueda con `lote_id = busqueda_id`, pasa `limites`).
- [ ] T042 [US1] Una corrida real contra Croma, avisada antes (1 request de 100, 1 crédito). Confirmar: forma de `departamento` (pregunta 9), NIT con o sin DV (pregunta 8), 4xx/5xx cobrados (pregunta 5). Segunda corrida idéntica: 0 créditos. Lo que cambie vuelve como Rojo en T029, no como parche.

## Fase 4: Pulido

- [ ] T043 [P] `docs/arquitectura-backend.md`: módulos `descubrimiento` y `costos`, puerto, registro, suite de contrato y cómo sumar un adaptador (pregunta abierta 12).
- [ ] T044 [P] `.claude/skills/slice-tdd/SKILL.md`: prefijo de rama `slice/` → `feature/`, como pide la spec.
- [ ] T045 Suite completa: `cd backend && uv run pytest -q && uv run lint-imports`, y `scripts/migrar_local.sh` dos veces sobre base vacía.

## Dependencias

- Setup (T001-T003) → Fundacional → US1 → Pulido.
- T004 → T005. T006 → T007 → T008 → T009 (T008 YAML real queda rojo hasta T031).
- T010 → T011 → T012 → T013 → T014.
- T014 → T015 → T016 → T017/T018 → T019.
- T019 → T020 → T021; T019 → T022 → T023; T019 → T024 → T025; T019 → T026 → T027.
- T007, T009, T025, T027 → T029 → T030 → T031 → T032 → T033 → T034-T037.
- T021, T031 → T038 → T039 → T040 → T041 → T042.
- T043-T045 al final.

## Paralelo

- Setup: T002 y T003 juntos.
- Paso 2: T006 y T008 (tests) en paralelo; sus Verde en orden.
- Paso 3: T010 en paralelo con el paso 2; T017 y T018 juntos; después de T019, T020, T022, T024 y T026 en paralelo.
- US1: T028 mientras se escribe T029; T034 y T036 en paralelo.
- Pulido: T043 y T044.

## Estrategia

MVP = la fase 3 completa: es el único incremento con valor (una búsqueda real deja leads). No hay entrega parcial útil antes de T041. Si el tiempo no alcanza, se corta T042 (la corrida real) y se anota, nunca un test de RLS, costos o dedup. `docs/arquitectura-backend.md` (T043) se puede reducir a un párrafo.
