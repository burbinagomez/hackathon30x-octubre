# Tasks: 002 — Puertos, registro de adaptadores y Supersociedades

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Tests**: obligatorios (constitución II). Cada **Rojo** se corre y se ve fallar **por la razón esperada** antes de su **Verde**. `ImportError` o `UndefinedTable` no cuentan como rojo de un test de comportamiento: donde la tabla o el módulo tienen que existir primero, el rojo es por **mutación** (se escribe la versión sin la propiedad, se ve el rojo, se agrega). Un test que nace verde se reescribe.
**Esqueleto antes del rojo:** en T006, T008, T020, T022, T024, T026, T029, T038, T040 y T046 se crea primero el esqueleto vacío de lo que se prueba (clase o función con `raise NotImplementedError` o retorno vacío) y cada test tiene que fallar por **su aserción**. Un `ImportError` no cuenta como rojo.
**Revisión**: el `advisor` revisa los tests marcados *(advisor)* antes de escribir su Verde.

Formato: `- [ ] T0NN [P] [US1] Rojo/Verde: qué, en qué archivo`. `[P]` = archivo distinto y sin dependencia de una tarea abierta. Rutas relativas a la raíz del repo.

La spec tiene una sola historia (US1: una búsqueda por CLI deja leads deduplicados con su costo y su cumplimiento). Las fases siguen el orden que fijó el dueño, no el número de paso: 1, 2, 3, 4, 7, 8, bloque Croma (5 + T035 + T046-T047 + T042), 6 y 9. Los IDs no se renumeran: el archivo se lee en orden de ejecución. El CLI arranca **sin adaptadores registrados**: el catálogo real queda `{}` hasta T031.

## Fase 1: Setup

- [X] T001 Mover `httpx` del grupo dev a `dependencies` y sumar `pyyaml` a `dependencies` en `backend/pyproject.toml`; `uv lock` actualiza `backend/uv.lock`. (La 004 y la 012 declaran la misma línea de `pyyaml`; el choque se resuelve en el merge siguiente.)
- [X] T002 [P] Agregar `croma_api_key: SecretStr | None = None` a `Settings` en `backend/app/config.py` (nunca en logs).
- [X] T003 [P] Crear los paquetes vacíos `backend/app/modulos/descubrimiento/{dominio,aplicacion,infraestructura/adaptadores,infraestructura/persistencia}/__init__.py`, `backend/app/modulos/costos/{dominio,infraestructura}/__init__.py` y `backend/tests/{contratos,unit/descubrimiento}/__init__.py` si hace falta.

## Fase 2: Fundacional (bloquea a US1)

### Paso 1: canario de capas

- [X] T004 Rojo: `backend/tests/arquitectura/test_import_linter.py::test_detecta_violacion_de_capas`. Copia `pyproject.toml` a `tmp_path`, escribe un `descubrimiento/dominio/x.py` que importa `descubrimiento.infraestructura`, corre `lint-imports` y espera código ≠ 0 y el nombre del contrato `layers`. Segundo canario en el mismo archivo, `test_descubrimiento_no_importa_costos_infraestructura`: un módulo de `descubrimiento` que importa `app.modulos.costos.infraestructura` rompe el contrato `forbidden` por nombre. Rojo: ninguno de los dos contratos existe.
- [X] T005 Verde: en `backend/pyproject.toml`, contrato `layers` (`infraestructura > aplicacion > dominio`) con **todos** los containers de `app.modulos.*` (`app.modulos.descubrimiento`, `app.modulos.costos`), y contrato `forbidden` `app.modulos.descubrimiento` ↛ `app.modulos.costos.infraestructura` (`app.cli` es la única raíz que los une). Primero se prueba la capa opcional `"(aplicacion)"` en el import-linter instalado; si no anda, respaldo: `backend/app/modulos/costos/aplicacion/__init__.py` vacío. Se alinea el Structure Decision de plan.md con lo que salga. `uv run lint-imports` verde sobre el repo real.

### Paso 2: dominio y registro

- [X] T006 [P] Rojo: `backend/tests/unit/descubrimiento/test_dominio.py`, `test_normalizar_nit[…]` y `test_cubre[…]`: `normalizar_nit("900.123.456-7") == "900123456"`, `normalizar_nit("900123456") == "900123456"`, `normalizar_nit("9001234567") == "9001234567"` (sin guion no se corta el DV, pregunta abierta 8); `cubre(meta, criterios)` por país, por `"*"` y por un filtro fuera de `meta.filtros`.
- [X] T007 Verde: en `backend/app/modulos/descubrimiento/dominio/`: `modelos.py` (`EmpresaCruda`, `Actividad`, `CriteriosICP`, `PaginaEmpresas`, `MetaFuente`, `cubre`), `nit.py` (`normalizar_nit`), `errores.py` (`CriterioNoSoportado`, `LimiteFuenteAgotado`, `FuenteNoDisponible`, `RegistroInvalido`), `puertos.py` (`FuenteDescubrimiento`, `RepositorioLeads`). En `backend/app/modulos/costos/dominio/`: `OperacionCosto` y `RegistroCostos`. Firmas exactas: plan.md, sección Puerto (`CriteriosICP.filtros: Mapping[str, str | tuple[str, ...]]`).
- [X] T008 [P] Rojo: `backend/tests/unit/descubrimiento/test_registro.py` con los 6 tests de la spec. El primero que se escribe es `test_carga_config_fuentes_yaml_real_sin_error` (YAML real, catálogo real): **queda en rojo hasta T031**, porque el catálogo recién tiene `croma_supersociedades_co` ahí; se commitea con `xfail(strict=True, raises=AssertionError)` y T031 le saca la marca. Los otros 5 (`test_solo_carga_adaptadores_habilitados`, `test_habilitado_sin_implementacion_se_reporta`, `test_fuente_habilitada_sin_paises_o_filtros_falla`, `test_deshabilitada_incompleta_no_se_valida`, `test_clave_del_catalogo_ausente_del_yaml_falla`) usan YAML en `tmp_path` y un catálogo de prueba con una clase falsa, y quedan verdes en T009.
- [X] T009 Verde: `cargar_registro(ruta_yaml, catalogo) -> Registro` en `backend/app/modulos/descubrimiento/aplicacion/registro.py`. Lee solo `fuentes_descubrimiento`, con `yaml.safe_load`.

### Paso 3: migración 0002, persistencia y siembra

- [X] T010 [P] Crear `backend/scripts/supabase_simulado.sql` (`anon` y `authenticated` `NOLOGIN`, `GRANT USAGE ON SCHEMA public TO anon, authenticated` y `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES` y `ON SEQUENCES TO anon, authenticated`) y sumarlo en `.github/workflows/ci.yml` como paso propio después de "roles.sql + password de test" y antes de "supabase/migrations desde vacío". Va primero, para que los tests de privilegios puedan nacer en rojo.
- [X] T011 `supabase/migrations/0002_descubrimiento.sql`, **primera versión, sin `ENABLE ROW LEVEL SECURITY`/políticas y sin el bloque `DO` de `REVOKE`** (base para los rojos por mutación): `tenants`, `busquedas` (`creado_en timestamptz NOT NULL DEFAULT now()`, `estado` NOT NULL DEFAULT `'creada'` CHECK `IN ('creada','terminada','con_errores')`), `leads` (`creado_en timestamptz NOT NULL DEFAULT now()`, `UNIQUE (tenant_id, pais, id_fiscal)`, `tipo_titular` NOT NULL DEFAULT `'desconocido'`, `idioma_contacto` GENERATED desde `pais`), `lead_fuentes` (`UNIQUE (lead_id, fuente, busqueda_id)`), `cumplimiento` (`lead_id` UNIQUE, `base_legal` nullable), `costos` (`gratis bool NOT NULL`, `ts` DEFAULT `now()`, índice `(tenant_id, proveedor, ts)`, CHECK cerrado de `tipo` con la lista exacta de plan.md, sección Datos, `overpass_query` incluido), `fuente_cache` (UNIQUE `(proveedor, endpoint, hash_params)`). FKs y `GRANT` a `app_rt` según plan.md, sección Datos.
- [X] T012 Rojo: con la `0002` en el repo, correr `backend/tests/arquitectura/test_migraciones.py::test_migrar_local_desde_vacio_dos_veces_sin_drift` y verlo fallar primero en `assert _drift(base_vacia) == []` (modelos.py vacío). El rojo `== "0001"` aparece recién con modelos.py declarado (T014); T013 va después de T014.
- [X] T013 Verde: reemplazar ese assert por la comparación contra las versiones de `supabase/migrations/*.sql` (ruta `BACKEND.parent / "supabase" / "migrations"`, versión = antes del primer `_`, orden de texto, unidas por coma).
- [X] T014 Verde: declarar las 7 tablas en `backend/app/modelos.py` (Core) hasta que `compare_metadata` dé vacío: tipos exactos (`UUID`, `JSONB`, `DateTime(timezone=True)`, `Numeric`), `UniqueConstraint` `(tenant_id, pais, id_fiscal)`, `(lead_id, fuente, busqueda_id)`, `cumplimiento.lead_id`, `(proveedor, endpoint, hash_params)`; `Index` `(tenant_id, proveedor, ts)`; todas las `ForeignKey`; `Computed(..., persisted=True)` para `idioma_contacto`. Deja T012 en rojo solo por `== "0001"`.
- [X] T015 Rojo *(advisor)*: `backend/tests/integration/test_privilegios_supabase.py::test_tenant_no_sobrevive_al_commit`, con la unidad de trabajo real sobre el engine de `app_rt`. Rojo por mutación: primera versión de la unidad de trabajo en `backend/app/db.py` con `set_config('app.tenant_id', :id, false)` (de sesión) → el tenant sobrevive al commit → rojo.
- [X] T016 Verde: unidad de trabajo en `backend/app/db.py` con `set_config('app.tenant_id', :id, true)` como primera sentencia de la transacción.
- [X] T017 [P] Rojo *(advisor)*: `backend/tests/integration/test_rls.py::test_tenant_b_no_accede_a_datos_de_a[tabla]` sobre `tenants, busquedas, leads, lead_fuentes, cumplimiento, costos`, usando la unidad de trabajo de T016. Como tenant B: SELECT vacío; UPDATE y DELETE afectan 0 filas de A; INSERT con el `tenant_id` de A rechazado. En `tenants` el INSERT lo rechaza la falta de privilegio: asertar `InsufficientPrivilege`. `fuente_cache` en la lista de exclusiones con su razón. Rojo por mutación: la `0002` de T011 no tiene RLS → B ve lo de A. En el mismo archivo, `test_tenant_b_no_cuelga_filas_de_un_lead_de_a[lead_fuentes|cumplimiento|lead_fuentes_busqueda]`: B inserta con su `tenant_id` y tiene que fallar con `ForeignKeyViolation` (23503). En los dos primeros, con el `lead_id` de A. En `lead_fuentes_busqueda`, con un lead suyo (`lead_b`, sembrado en el fixture `datos`) y el `busqueda_id` de A. Rojo por assert (`DID NOT RAISE`): las FK simples a `leads(id)` y `busquedas(id)` no pasan por RLS y el insert entra. `costos.lead_id` y `costos.lote_id` siguen sin FK, por decisión de la spec. Guarda `test_la_lista_cubre_todas_las_tablas_de_public`: las tablas de `public` son `TABLAS ∪ EXCLUIDAS`. Se vio roja por `alembic_version`, un resto del 001 en pg001 local, y esa tabla se borró de esa base (CI arranca vacía). La 003 tiene que tocar esta lista cuando sume tablas.
- [X] T018 [P] Rojo *(advisor)*: en `backend/tests/integration/test_privilegios_supabase.py`, `test_anon_y_authenticated_sin_privilegios[rol]` (un caso por rol, ver el `ponytail:` en `test_privilegios_supabase.py:56-57`; tablas de `pg_tables` en runtime, con assert previo de que incluye `leads`; `SELECT`, `INSERT`, `UPDATE`, `DELETE` y `TRUNCATE`) y `test_default_privileges_no_conceden_a_anon_ni_authenticated` (tabla regular `public.x`, no `TEMP`, con rollback). Rojo por mutación: la `0002` de T011 no tiene el bloque `DO` de `REVOKE` y `supabase_simulado.sql` concedió todo. El escenario sin `anon`/`authenticated` lo cubre `base_vacia` de `test_migraciones.py`.
- [X] T019 Verde: agregar a `supabase/migrations/0002_descubrimiento.sql` el `ENABLE ROW LEVEL SECURITY` + políticas `USING/WITH CHECK` (en `tenants`, `USING (id = …)`) y, al final, el bloque `DO` de `REVOKE` condicionado a `pg_roles`. `UNIQUE (tenant_id, id)` en `leads` y en `busquedas`, y tres FK compuestas: `lead_fuentes (tenant_id, lead_id) → leads`, `lead_fuentes (tenant_id, busqueda_id) → busquedas` y `cumplimiento (tenant_id, lead_id) → leads`. Los dos `UniqueConstraint` y las tres `ForeignKeyConstraint` se declaran también en modelos.py; si no, el drift de T012/T013 sale rojo. `costos` sigue sin FK. Antes del verde, reaplicar la 0002 en pg001. T017 y T018 en verde; T012 sigue verde.
- [ ] T020 [P] Rojo *(advisor)*: `backend/tests/integration/test_leads_repo.py`:
  - `test_unico_por_tenant_pais_id_fiscal` y `test_unico_lead_fuente_busqueda` (los de la spec);
  - `test_lead_persistido_conserva_tipo_titular`: una `EmpresaCruda` de Supersociedades guardada y releída tiene `tipo_titular == 'juridica'`;
  - `test_lead_nuevo_y_cumplimiento_en_una_transaccion`: forzar un fallo al insertar el `cumplimiento` (monkeypatch del INSERT de cumplimiento para que lance) → 0 filas en `leads`;
  - `test_crear_busqueda_se_confirma_antes`: `crear_busqueda` deja la fila visible desde otra conexión antes de que se llame a ningún adaptador.
- [ ] T021 Verde: `backend/app/modulos/descubrimiento/infraestructura/persistencia/repositorio_leads.py`: `obtener_o_crear_lead(e, licencia)` inserta lead + `cumplimiento` en una transacción cuando es nuevo; `crear_busqueda` y `cerrar_busqueda` en transacción propia; `agregar_lead_fuente` con `ON CONFLICT DO NOTHING`.
- [ ] T022 [P] Rojo: `backend/tests/integration/test_sembrar_tenant.py`, los 2 tests de la spec: `test_sembrar_dos_veces_mismo_id_actualiza` (upsert por `id` con `nombre` e `idioma` nuevos) y `test_no_imprime_la_url_de_postgres` (`getpass` con monkeypatch, exit ≠ 0, la password no aparece en stdout/stderr).
- [ ] T023 Verde: `backend/scripts/sembrar_tenant.py`.

### Paso 4: libro de costos en Postgres

- [ ] T024 Rojo *(advisor)*: `backend/tests/integration/test_costos_repo.py`, contadores sembrados relativo a `now()` de la DB con `unidades` 0, 1 y 10: `test_requests_24h_cuenta_filas_en_ventana` (23 h 59 min sí, 24 h 01 min no, aunque la de adentro tenga `unidades=0`); `test_creditos_mes_suma_unidades_del_mes_calendario_utc` (con `SET TIME ZONE 'America/Bogota'`); `test_registrar_sobrevive_al_rollback_de_otra_transaccion` (pregunta abierta 1).
- [ ] T025 Verde: `backend/app/modulos/costos/infraestructura/postgres_costos.py`, con transacción propia por `registrar`.
- [ ] T026 [P] Rojo: `backend/tests/integration/test_costos_repo.py`, `test_cache_misma_clave_pisa_respuesta` (misma `(proveedor, endpoint, hash_params)` → 1 fila con la segunda respuesta) y `test_cache_lectura_devuelve_respuesta_y_as_of`.
- [ ] T027 Verde: `backend/app/modulos/descubrimiento/infraestructura/persistencia/repositorio_cache.py`, con transacción propia por upsert.

**Checkpoint**: dominio, registro, migración y persistencia en verde.

## Fase 3: US1 sin adaptadores, caso de uso y CLI

**Objetivo**: `uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11` corre de punta a punta con el catálogo vacío. Crea y cierra la búsqueda y reporta `sin_fuente_para` y `sin_implementacion`. Con una fuente falsa inyectada, deja leads deduplicados, con costo y cumplimiento.
**Prueba independiente**: los tests de esta fase, sin red y sin Croma.

### Paso 7: caso de uso

- [ ] T038 [US1] Rojo *(advisor)*: `backend/tests/unit/descubrimiento/test_ejecutar_busqueda.py`, los 8 tests de la spec con fuentes y repositorio falsos (los falsos en memoria de `RepositorioLeads`, `RegistroCostos` y caché van en `backend/tests/falsos.py`, porque T040 los reusa): `test_mismo_nit_de_dos_fuentes_queda_en_un_lead`, `test_misma_fuente_repetida_no_duplica_lead_fuentes`, `test_nit_con_y_sin_formato_es_el_mismo_lead`, `test_mismo_nit_distinto_pais_son_dos_leads`, `test_lead_existente_en_segunda_busqueda_no_duplica_cumplimiento`, `test_cada_lead_nuevo_tiene_fila_en_cumplimiento`, `test_sin_fuente_para_el_pais_se_reporta` (con una fuente falsa que solo cubre `CO`; no necesita el catálogo real) y el octavo, `test_error_de_fuente_se_reporta_y_busqueda_queda_con_errores`: el resultado reporta `LimiteFuenteAgotado`/`FuenteNoDisponible` por fuente sin tragarlos y la búsqueda cierra `con_errores` (pregunta 11). La fuente falsa devuelve el NIT **sin** normalizar (`900.123.456-7`), así que la clave de dedup tiene que pasar por `normalizar_nit` en el caso de uso; si no, `test_nit_con_y_sin_formato_es_el_mismo_lead` queda rojo.
- [ ] T039 [US1] Verde: `backend/app/modulos/descubrimiento/aplicacion/ejecutar_busqueda.py` (`crear_busqueda` → adaptadores → `obtener_o_crear_lead` + `agregar_lead_fuente` → `cerrar_busqueda`), sin importar `infraestructura` (lo cuida T005).

### Paso 8: CLI sin adaptadores

- [ ] T040 [US1] Rojo: `backend/tests/unit/test_cli.py`, sin red y sin Postgres. El esqueleto es `main(argv=None, *, catalogo=catalogo, persistencia=None) -> int`, que devuelve 0 sin imprimir. `catalogo` por defecto es el real de `infraestructura/adaptadores` y `persistencia=None` arma `postgres_costos` y los repositorios de Postgres desde `settings`. Los tests pasan los falsos de `backend/tests/falsos.py` (T038) por `persistencia`, y la fuente falsa por `catalogo`. **Ningún falso vive en `app/`.** Los 4 tests:
  - `test_buscar_sin_tenant_falla`;
  - `test_buscar_imprime_resumen`: `fuentes.yaml` real y `catalogo={"croma_supersociedades_co": FuenteFalsa}`. Como la entrada es `proveedor: croma`, el test pone una `CROMA_API_KEY` falsa por monkeypatch. `FuenteFalsa` vive en `test_cli.py`, acepta los kwargs del constructor que arma el CLI, registra 1 fila en el `RegistroCostos` que recibe y devuelve 2 `EmpresaCruda` con el mismo NIT (`900.123.456-7` y `900123456`). Imprime encontrados 2 · únicos 1 · nuevos 1 · créditos 1 · `sin_implementacion` `croma_dian_trade_co, osm_overpass`;
  - `test_buscar_sin_adaptadores_reporta_sin_fuente_y_sin_implementacion`: `fuentes.yaml` real y `catalogo={}` explícito, no el real, así sigue verdadero después de T031. Con `--pais CO --ciiu 4711 --departamento 11` sale con código 0 y la búsqueda queda `terminada`, no `con_errores`, porque no falló ninguna fuente. Imprime `sin_fuente_para: CO` y `sin_implementacion: croma_dian_trade_co, croma_supersociedades_co, osm_overpass`, ordenado. El `RegistroCostos` falso tiene 0 filas y el repositorio, 0 leads. No exige `croma_api_key`: `settings` sin key;
  - `test_salida_no_contiene_secretos`: ni API key ni `DATABASE_URL`.
  Rojo: con el esqueleto, cada uno falla por su aserción. `test_buscar_sin_tenant_falla` falla porque el esqueleto sale con 0, y los demás porque no imprime nada. `test_salida_no_contiene_secretos` asierta además que hay salida, así no nace verde.
- [ ] T041 [US1] Verde: `backend/app/cli.py`, raíz de composición. Lee `fuentes.yaml` (registro y `limites`), arma los adaptadores por búsqueda con `lote_id = busqueda_id` y les pasa `limites`. Todavía no lee `tarifas.yaml`, porque eso llega con T046-T047. La `croma_api_key` se lee solo si hay que construir un adaptador de `proveedor: croma`. Sin key y con uno de esos en `registro.fuentes`, sale con código ≠ 0 y un mensaje sin secretos.

**Checkpoint (MVP)**: T041 en verde. Ver Estrategia.

## Fase 4: bloque Croma

**Objetivo**: el mismo comando trae leads reales de Supersociedades.
**Prueba independiente**: los tests de esta fase, sin red, y al final una corrida real en T042.

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
  - `test_error_no_se_cachea`: tras un 4xx y tras 5xx agotados, el caché sigue vacío y la siguiente llamada sí hace request;
  - `test_respuesta_200_que_no_parsea_no_se_cachea`: un 200 con el cuerpo truncado, o sin `data` ni `total`, cumple `pytest.raises(FuenteNoDisponible)`, y el mensaje no incluye el cuerpo ni la API key. El caché queda vacío. Escribe 1 fila con `unidades=1` y `costo_unitario == tarifas.croma.usd_por_credito`. Sabotajes que lo ponen en rojo: el upsert del caché antes del parseo, o el fallo de parseo registrado con `unidades=0`.
  Rojo: tras el esqueleto vacío de la clase, cada test falla por su aserción.
- [ ] T030 [US1] Verde: `backend/app/modulos/descubrimiento/infraestructura/adaptadores/croma_supersociedades.py`, en el orden de plan.md (validar → body → caché → límite antes de cada intento → request con reintento → fila por intento → solo en 200: mapeo y después caché). API key desde el constructor, solo en el header, nunca en el mensaje de un error.
- [ ] T031 [US1] Registrar `{"croma_supersociedades_co": CromaSupersociedades}` en `backend/app/modulos/descubrimiento/infraestructura/adaptadores/__init__.py`. `test_carga_config_fuentes_yaml_real_sin_error` (T008) pasa a verde.
- [ ] T032 [US1] Rojo *(advisor)*: en `backend/tests/integration/test_costos_repo.py`, `test_croma_consulta_escribe_fila_en_costos` (adaptador con transporte falso + `postgres_costos` real: 1 fila con `tipo='croma_consulta'`, `unidades=1`, `costo_unitario=0.00099`, `gratis=true`, `tenant_id` del contexto) y `test_reintento_cuenta_para_el_limite` (98 filas previas de `unidades=1`; 502 con `unidades=0` + 200 con `unidades=1` → 100 filas, `requests_24h == 100`, `creditos_mes` de 98 a 99, la siguiente búsqueda lanza `LimiteFuenteAgotado`). Rojo por mutación: con `registrar` del adaptador comentado, 0 filas; y con `requests_24h` contando `SUM(unidades)` en vez de `COUNT(*)`, el contador da 99 y la búsqueda siguiente no corta.
- [ ] T033 [US1] Verde: lo que T032 exija en el adaptador o en `postgres_costos`, sin tocar los tests unitarios.

### Contrato de Croma y tarifa

- [ ] T035 [US1] Verde (se adelanta al paso 6; el rojo de su contrato lo da T034): `backend/tests/contratos/fabricas.py` con la fábrica de `croma_supersociedades_co` (transporte falso + fixture de T028).
- [ ] T046 [US1] Rojo: `backend/tests/unit/test_cli.py::test_tarifa_croma_es_decimal_exacto`, sacado de T040. Con `catalogo={"croma_supersociedades_co": FuenteFalsa}`, que captura el `costo_unitario` que le pasa el CLI, `costo_unitario == Decimal("0.00099")` y `isinstance(costo_unitario, Decimal)`. El rojo es real: la primera versión lee `tarifas.yaml` con `yaml.safe_load` y pasa el valor tal cual, un `float`, así que `isinstance` falla y `0.00099 != Decimal("0.00099")`.
- [ ] T047 [US1] Verde: `app/cli.py` carga `tarifas.yaml` una vez, con cada valor como `Decimal(str(v))`, y le pasa al adaptador el `costo_unitario` ya resuelto.

### Corrida real

- [ ] T042 [US1] Cierra el bloque, después de T033 y T047. Una corrida real contra Croma, avisada antes (1 request de 100, 1 crédito). Confirmar: forma de `departamento` (pregunta 9), NIT con o sin DV (pregunta 8), 4xx/5xx cobrados (pregunta 5). Segunda corrida idéntica: 0 créditos. Lo que cambie vuelve como Rojo en T029, no como parche.

## Fase 5: Paso 6, contrato y adaptadores declarados

- [ ] T034 [P] [US1] Rojo: `backend/tests/contratos/test_fuente_descubrimiento.py` parametrizado sobre `catalogo`, con `assert catalogo` a nivel de módulo, `test_hay_fabrica_para_cada_clave_del_catalogo` y los 3 tests de la spec (plan.md, sección Suite de contrato). Criterio no soportado con la clave centinela `"__criterio_inexistente__"`, no una real. Va después del bloque Croma: con el catálogo vacío, el `assert catalogo` rompe la colección. Rojo real de cada uno, corriéndolo una vez con una fábrica de adaptador falso en lugar de la de T035:
  - `test_devuelve_empresas_normalizadas`: `as_of` sin zona, o `fuente` distinta de la clave;
  - `test_registra_costo_antes_de_devolver`: el adaptador no llama a `registrar`;
  - `test_rechaza_criterio_no_soportado`: el adaptador hace el request antes de validar.
- [ ] T036 [P] [US1] Rojo: `backend/tests/arquitectura/test_registro_adaptadores.py` (`test_todo_adaptador_de_registro_esta_declarado` y `test_persistencia_solo_contiene_excluidos_y_no_importa_http`, con `EXCLUIDOS` de la spec ya enmendado a `costos/infraestructura/postgres_costos.py`) y `backend/tests/arquitectura/test_costos_por_adaptador.py::test_todo_adaptador_de_registro_recibe_registro_costos`. Los dos recorridos afirman que encontraron **al menos una** clase antes de chequearla. Solo chequean puertos que existen hoy. Las funciones de recorrido reciben la raíz por parámetro (el test real pasa `app/modulos`), así el rojo en `tmp_path` corre el mismo código: una clase fuera del catálogo / sin `RegistroCostos` / un archivo extra en `persistencia/` → rojo.
- [ ] T037 [US1] Verde: lo que T036 exija sobre el código real.

## Fase 6: Pulido

- [ ] T043 [P] `docs/arquitectura-backend.md`: módulos `descubrimiento` y `costos`, puerto, registro, suite de contrato y cómo sumar un adaptador (pregunta abierta 12).
- [ ] T044 [P] `.claude/skills/slice-tdd/SKILL.md`: prefijo de rama `slice/` → `feature/`, como pide la spec.
- [ ] T045 Suite completa: `cd backend && uv run pytest -q && uv run lint-imports`, y `scripts/migrar_local.sh` dos veces sobre base vacía.

## Dependencias

- Setup (T001-T003) → Fundacional (pasos 1-4) → US1 sin adaptadores (pasos 7-8) → bloque Croma → paso 6 → Pulido.
- T004 → T005. T006 → T007 → T008 → T009.
- `test_carga_config_fuentes_yaml_real_sin_error` (T008) sigue en rojo hasta T031, y T031 cae en el bloque Croma, al final. Mientras tanto queda marcado `xfail(strict=True, raises=AssertionError, reason="rojo hasta T031: el catálogo todavía no tiene croma_supersociedades_co")`, sin cambios en el código.
  - `strict` hace que, si algo lo pone verde antes de tiempo, la suite falle y obligue a sacar la marca.
  - `raises=AssertionError` hace que cualquier otra excepción falle de verdad. Un ejemplo es `RegistroInvalido`, por una clave del catálogo que falte en el YAML.
  - T031 le saca la marca. Las fases 3 y 4 no lo tocan: T040 inyecta su catálogo, no usa el real.
- T010 → T011 → T012 → T014 → T013.
- T013 → T015 → T016 → T017/T018 → T019.
- T019 → T020 → T021; T019 → T022 → T023; T019 → T024 → T025; T019 → T026 → T027.
- T007, T009, T021 → T038 → T039. T038 ya no depende de T031.
- T039 → T040 → T041; T025, T027 → T041 (la `persistencia` por defecto). T040 depende de T039.
- T007, T009, T025, T027 → T029 → T030 → T031 → T032 → T033 → T035. T028 se escribe junto con T029.
- T041 → T046 → T047. El test de tarifa necesita el CLI, no el adaptador.
- T033, T047 → T042. La corrida real lleva el adaptador y la tarifa en `Decimal`.
- T031, T035 → T034; T031 → T036 → T037. El paso 6 va después del bloque Croma: con el catálogo vacío, `assert catalogo` y "al menos una clase" no tienen qué recorrer.
- T043-T045 al final.

## Paralelo

- Setup: T002 y T003 juntos.
- Paso 2: T006 y T008 (tests) en paralelo; sus Verde en orden.
- Paso 3: T010 en paralelo con el paso 2. T017 y T018 juntos. Después de T019, T020, T022, T024 y T026 en paralelo.
- Pasos 7-8: T038 puede escribirse en cuanto T021 esté verde, en paralelo con T024-T027. T040 espera a T039.
- Bloque Croma: T028 mientras se escribe T029. T046 en paralelo con T029-T033, porque solo depende de T041.
- Paso 6: T034 y T036 en paralelo.
- Pulido: T043 y T044.

## Estrategia

Incremento tras T041, sin Croma:
- el CLI corre de punta a punta contra Postgres con RLS por tenant;
- crea y cierra la búsqueda;
- reporta `sin_fuente_para` y `sin_implementacion` con el `fuentes.yaml` real.

Con una fuente falsa inyectada, ya está probado lo que cualquier fuente va a heredar: dedup por `(pais, id_fiscal)`, `lead_fuentes`, `cumplimiento` en la misma transacción que el lead, y la fila de `costos` escrita por el adaptador. No trae leads reales: eso es el bloque Croma.

Si el tiempo no alcanza, se corta en este orden:
1. T043 se reduce a un párrafo. Después, T044.
2. T042, la corrida real, y se anota que no se hizo.
3. El bloque Croma entero (T028-T033, T035, T046, T047, T042) junto con el paso 6 (T034-T037). Van juntos: sin adaptador, el contrato no tiene qué recorrer, y la constitución no deja registrar un adaptador sin su suite de contrato. Si Croma entra, entran con él T046-T047 (sin `Decimal`, el libro de costos queda mal) y el paso 6.

Nunca se corta un test de RLS, de costos ni de dedup.
