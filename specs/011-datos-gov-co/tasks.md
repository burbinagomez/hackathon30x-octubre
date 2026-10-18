# Tasks: 011 — datos.gov.co (`c82u-588k`), segunda fuente de descubrimiento, con contrato

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Prerequisites**:
- La 002 y la 003 mergeadas en `main`, y `main` mergeado en esta rama (con merge, no rebase).
- D1–D12 resueltas. Con D7, los 6 tests que dependen de la 005 se movieron a `specs/005` (ver "Movidos a specs/005").

> Formato de `/speckit-tasks` aplicado a mano: `setup-plan.sh` no resuelve el feature.

**Formato**: `- [ ] TNNN [MIN?] [P?] [Paso n] Descripción`
- **[MIN]**: sin esta tarea, datos.gov.co no devuelve leads guardados por tenant que se puedan ver en el tablero. Se hace primero. Todo lo que no lleva [MIN] está en la Fase Pulido, al final.
- **[P]**: se puede hacer en paralelo, porque toca otro archivo y no depende de una tarea abierta.
- **[Paso n]**: el paso del "Plan de tareas" de la spec.
- **[002]** / **[003]**: la tarea necesita código de esa slice en `main`.
- **Rojo real.** Cada **Rojo** se corre y tiene que fallar **por aserción**. Un `ImportError`, un `AttributeError` o un `NotImplementedError` no cuentan. Por eso los stubs existen antes que su test, y los campos nuevos se leen con `getattr(x, "campo", None)` en el primer rojo. Vale también para las [MIN].
- **Guardas.** Una guarda que nace verde se comprueba **por mutación**: se rompe a mano la implementación, se ve el rojo y se revierte. El commit no lleva la mutación.
- **(advisor)**: el advisor revisa el test antes de pasar al Verde.
- **Bloqueada por Dn**: no se empieza hasta que la pregunta n de `plan.md` esté resuelta.

Comando de la suite: `cd backend && uv run pytest -q && uv run lint-imports`.

---

## Mínimo funcional

### Fase 1: Setup y puerta

- [ ] T001 [MIN] **Puerta (D12).**
  - La 002 y la 003 están en `main`.
  - `git fetch && git merge origin/main` en `feature/011-datos-gov-co`. Si hay conflictos, se para y se avisa.
  - Las respuestas a D1–D11 quedan anotadas en `plan.md`.
  - Ninguna tarea marcada [002] o [003] arranca sin esto.
- [ ] T002 [MIN] Se confirma que `pyyaml` y `httpx` ya están en `[project].dependencies` (`pyyaml` lo agrega la 002). **No se toca `pyproject.toml`.** `uv run lint-imports` en verde.
- [X] T003 [MIN] [P] Fixtures sintéticas en `backend/tests/fixtures/datos_gov_co/`. Las tres usan el esquema real de `c82u-588k`, NITs ficticios con el formato `9\d{8}` y ninguna razón social real.
  - `filas.json`: empresas válidas con las 7 columnas del `$select`.
  - `filas_descartables.json`: las válidas más un caso de cada tipo, de (a) a (d), más (a'), una natural escrita `"Persona Natural "` (mayúsculas mezcladas y un espacio al final).
  - `conteo_naturales.json`, con `[{"count": "26304"}]`. Lo usa recién la Fase Pulido, pero se escribe junto con las otras dos.

**Checkpoint**: la rama está al día con `main` y la suite de la 002 y la 003 está en verde sin cambios.

### Fase 2: Skills (Paso 1), sin bloqueo

- [X] T004 [MIN] [P] [Paso 1] Cambios en `.claude/skills/fuentes-publicas/SKILL.md`. *[MIN dudosa: es doc, pero la línea 56 hoy le dice a cualquier lead que saque `tipo_titular` de `clase_identificacion`, y eso deja pasar naturales.]*
  - Línea 39, la fila de `datos_gov_co_rues`:
    - `c82u-588k`;
    - `filtros: [ciiu, departamento]`;
    - la condición de jurídica se aplica en el servidor sobre `organizacion_juridica`;
    - `trae: [nit, nombre, ciiu, ciudad_camara]`;
    - "conectado".
  - Línea 56: `tipo_titular` de datos.gov.co sale de `organizacion_juridica` y **no** de `clase_identificacion`, porque la clase NIT incluye naturales.
- [X] T005 [MIN] [P] [Paso 1] Cambios en `.claude/skills/cumplimiento-datos/SKILL.md`. *[MIN dudosa, por la misma razón que T004: regla 1.]*
  - Regla 1: la misma corrección que en T004.
  - Regla 4: una nota de que una fuente que permite filtrar en el servidor cuenta las naturales en lugar de guardarlas.

### Fase 3: Cámaras (Paso 2), sin bloqueo

*[MIN dudosa: sin cámaras no hay filtro por departamento, y la selección de fuentes de la 003 da `sin_geografia`. Las 58 completas pasan a Pulido (T054), que es el corte 4 de la spec.]*

- [X] T006 [MIN] [Paso 2] Stub `backend/app/modulos/descubrimiento/aplicacion/camaras.py`, con `Camara(codigo, nombre, municipio_sede, departamentos)` y dos funciones:
  - `cargar_camaras(ruta) -> {}`;
  - `camaras_de(camaras, departamento) -> set()`.

  Y `backend/config/camaras_co.yaml` vacío (`{}`).
- [X] T007 [MIN] [Paso 2] **Rojo:** `backend/tests/unit/descubrimiento/test_camaras_co.py::test_bogota_y_cundinamarca`. Falla por aserción: `set() != {"04"}`.
- [X] T008 [MIN] [Paso 2] **Verde:** `camaras_co.yaml` con las cámaras 04, 14, 47 y 58, y su cargador.

### Fase 4: Filtro jurídico (Paso 4) [002], bloqueada por D1, D9 y (advisor)

- [ ] T012 [MIN] [002] [Paso 4] Stub del adaptador en `infraestructura/adaptadores/datos_gov_co_rues.py`.
  - Clase `DatosGovCoRues` con el constructor del plan: transporte, reloj, dormir, `RegistroCostos`, caché, cámaras, tarifas, `lote_id`, meta, `url` y `app_token`. En el mínimo, el caché y el token pueden llegar en `None`, y la `url` es la constante pública del dataset.
  - `buscar` devuelve `PaginaEmpresas` vacía y no hace requests.
  - **Todavía no** entra al catálogo: eso es T040.
- [ ] T013 [MIN] [Paso 4] **Rojo (advisor):** `backend/tests/unit/descubrimiento/test_datos_gov_co.py::test_query_filtra_juridicas_en_servidor`.
  - Arranca con `assert len(capturadas) == 1`, antes de indexar, para que el rojo sea una aserción y no un `IndexError`.
  - Después toma la request de filas y afirma cada cláusula del `$where` de la spec, `$limit=5000` y que no haya `$order`, `$offset` ni `$group`.
  - Falla por aserción en el `len`: hay 0 requests capturadas.
- [ ] T014 [MIN] [Paso 4] **Rojo (advisor):** `::test_select_no_pide_columnas_de_personas`.
  - `$select` igual a la lista exacta de 7 columnas.
  - Un `for` sobre las 8 columnas prohibidas, enumeradas en el test, que afirma que ninguna está.
- [ ] T015 [MIN] [Paso 4] **Rojo (advisor):** `::test_cliente_descarta_lo_que_no_debio_llegar`, con `filas_descartables.json`.
  - Ningún `id_fiscal` ni `nombre` de los casos (a), (a'), (b), (c) ni (d) aparece en `empresas`.
  - La cantidad de empresas es igual a la cantidad de válidas.
  - El assert de `descartados_no_juridica == 5` se suma en T021 (Pulido), cuando el campo exista.
- [ ] T016 [MIN] [Paso 4] **Guarda (advisor):** `::test_descartados_no_se_loguean`.
  - `caplog.set_level(DEBUG)` sobre el root, que incluye `httpx`. Ningún `record.getMessage()` ni `record.args` contiene el `nit` ni la `razon_social` de (a), (a') a (d).
  - **Mutación:** un `logger.debug(fila)` en el descarte → rojo. Se revierte.
- [X] T017 [MIN] [Paso 4] **Advisor:** revisa T013–T016 antes del verde. Sus hallazgos se aplican y se vuelve a pedir revisión hasta APRUEBA.
- [X] T018 [MIN] [Paso 4] **Verde:**
  - armado del SoQL desde criterios ya validados;
  - `_es_juridica_valida(fila)` pura, que en (a) compara con `strip().upper()`;
  - mapeo mínimo para que las válidas salgan.
  - valida el CIIU con `^\d{4}$` antes de cualquier request (`CriterioNoSoportado`; rechaza tuplas y cualquier no-`str`).

**Checkpoint**: el principio VII queda cubierto en las dos capas.

### Fase 5: Resto del adaptador (Paso 6) [002] [003], bloqueada por D4, D9 y (advisor) en costos

- [X] T023 [MIN] [P] [Paso 6] **Rojo:** `::test_departamento_se_traduce_a_camaras`. *[MIN: el caso del CIIU inyectado es la guarda contra inyección SoQL.]*
  - 25 → `in('04','14','47','58')`.
  - Un departamento fuera del YAML y el CIIU `"47' OR '1'='1"` → `CriterioNoSoportado` y 0 requests.
  - Si el caso 11 → `'04'` ya pasa por T018, se comprueba por mutación.
  - La validación `^\d{4}$` del CIIU (que T018 ya trae) se comprueba por mutación: quitarla debe poner en rojo el caso inyectado.
- [X] T024 [MIN] [P] [003] [Paso 6] **Rojo:** `::test_mapea_fila_a_empresa_cruda`. Afirma los campos de la spec que existan en `EmpresaCruda` después de la 003, más `adaptador.meta.licencia == "CC-BY-SA-4.0"`. La licencia va en `meta`, no en `EmpresaCruda` (D4).
- [X] T025 [MIN] [P] [Paso 6] **Rojo:** `::test_as_of_sale_del_header`, con el header y sin él (reloj inyectable). *[MIN: `test_habilitada_por_yaml_temporal_da_leads_cc_by_sa` (T043) exige el `as_of` del header en el lead.]*
- [X] T027 [MIN] [P] [Paso 6] **Rojo:** `::test_pagina_2_vacia_sin_request`. Afirma 0 requests y 0 filas de costo. *[MIN: sin `$offset`, una página 2 traería otra vez las mismas filas y las mismas filas de costo.]*
- [X] T028 [MIN] [Paso 6] **Verde** de T023, T024, T025 y T027.
- [ ] T029 [MIN] [Paso 6] **Rojo (advisor):** dos tests de costos. *[MIN: principio de costos, todo adaptador de salida escribe su fila antes de devolver.]*
  - `::test_registra_segundos_de_cada_intento`, con 503 → 200 en filas a 2 s y 3 s. En el mínimo quedan 2 filas `socrata_descarga` con `unidades` 2 y 3, `Decimal(str(computo_seg_usd))`, `proveedor="datos.gov.co"`, `gratis=False`, `lead_id=None` y el `lote_id`. La tercera fila, la del conteo a 1 s, se suma en T021 (Pulido).
  - `::test_segundo_fallo_lanza_fuente_no_disponible`: dos 503 (y la variante con dos `httpx.TimeoutException`) dan `FuenteNoDisponible`, 2 filas y un `str(exc)` que no contiene el cuerpo de la respuesta (un marcador `"CUERPO-SECRETO"`). El assert de "0 requests de conteo" se suma en T021.
  - El advisor revisa antes del verde, hasta APRUEBA.
  - **Rojo escrito** con `xfail(strict, raises=AssertionError)` y el helper `_buscar_sin_propagar`, para que el rojo sea un assert y no un `HTTPStatusError`. El `xfail` se saca en T030.
  - **Duda para el advisor:** sin `departamento` en los criterios, T018 lanza `CriterioNoSoportado`. La spec no lo dice (el flujo 4 solo valida el CIIU y traduce el departamento). ¿Debe `departamento` ser obligatorio, o su ausencia debe omitir la cláusula `codigo_camara`? Además, T018 valida el NIT con `^\d{9}$` y la spec (caso c) dice `^[89]\d{8}$`.
- [ ] T030 [MIN] [Paso 6] **Verde:** el bucle de 2 intentos.
  - Registra la fila **antes** de decidir.
  - La espera pasa por `dormir`, que no se mide.
  - `FuenteNoDisponible` lleva solo el status.
- [ ] T036 [MIN] [002] [Paso 6] **Guarda (advisor):** `backend/tests/integration/test_costos_repo.py::test_socrata_descarga_escribe_fila_en_costos`, con `postgres_costos` real, rol `app_rt` y `SET LOCAL` del tenant. *[MIN: es la prueba de tenant y de rol `app_rt` sobre `costos`.]*
  - Valida `unidades == Decimal(2)`, el `costo_unitario` como `numeric`, `gratis=false` y el `tenant_id`.
  - **Nace verde**, porque el CHECK de `costos.tipo` de la 002 ya incluye `socrata_descarga` (plan 002, línea 210) y el adaptador ya registra desde T030.
  - **Mutación:** registrar `unidades=0` (falla `== Decimal(2)`) o un `tipo` fuera del CHECK (falla la constraint) tiene que ponerlo en rojo. Se revierte.
- [ ] T037 [MIN] [Paso 6] El advisor revisa la guarda T036 y su mutación, hasta APRUEBA. No hay código nuevo.

**Checkpoint**: `test_datos_gov_co.py` y `test_costos_repo.py` en verde, sin `xfail`.

### Fase 6: Registro, contrato e integración (Pasos 7 y 8) [002] [003], bloqueada por D10 y D11

- [ ] T038 [MIN] [003] [Paso 7] **Rojo:** dos tests, uno real y uno que puede nacer verde.
  - `test_registro.py::test_carga_config_fuentes_yaml_real_sin_error` se invierte: `datos_gov_co_rues` se carga, no está en `sin_implementacion`, y su entrada tiene `dataset == "c82u-588k"`, `filtros == ["ciiu", "departamento"]` y `licencia == "CC-BY-SA-4.0"`. Rojo real, porque hoy está en `false` con `nb3d-v3n7`.
  - `test_seleccion_fuentes.py::test_datos_gov_co_habilitada_recibe_ciiu_y_departamento`, con un registro en memoria. Si nace verde, porque la 003 ya trata `departamento` como geografía, se comprueba por mutación quitando `departamento` de los filtros, lo que da `sin_geografia`.
- [ ] T039 [MIN] [P] [002] [Paso 7] Fábrica `datos_gov_co_rues` en `backend/tests/contratos/fabricas.py`, con `MockTransport` y `filas.json`. *[MIN: la constitución exige que todo adaptador pase la suite de contrato de su puerto.]*
- [ ] T043 [MIN] [002] [003] [Paso 8] **Rojo (D11):** `backend/tests/integration/test_conectar_desconectar.py`, 3 de los 5 tests de la spec. Se escriben **antes** del verde de T040.
  - `::test_yaml_real_consulta_datos_gov_co`: rojo real, porque el YAML real todavía tiene `habilitado: false` y la búsqueda hace 0 requests al transporte de datos.gov.co.
  - `::test_habilitada_por_yaml_temporal_da_leads_cc_by_sa`: rojo real, porque el adaptador todavía no está en el catálogo y la búsqueda deja 0 leads. Si el rojo sale por excepción del loader y no por aserción, se ajusta el test antes de seguir. Es el test del mínimo: los leads quedan guardados por tenant, con `cumplimiento` y la fila de `costos`, leídos con `app_rt` y `SET LOCAL` del tenant. El aislamiento entre tenants de `leads` lo prueba `test_rls.py` de la 002.
  - `::test_deshabilitada_por_yaml_temporal_no_toca_datos_gov_co`: guarda. Nace verde; la mutación es poner `habilitado: true` en la copia temporal.
  - Los otros 2 (`test_naturales_se_guardan_como_conteo` y `test_mismo_nit_que_supersociedades_fusiona_por_regla_1`) pasan a T055 (Pulido).
- [ ] T040 [MIN] [002] [003] [Paso 7] **Verde, en UN commit:**
  - `fuentes.yaml` con `habilitado: true`, `dataset: c82u-588k`, `filtros: [ciiu, departamento]` y `trae: [nit, nombre, ciiu, ciudad_camara]`. `cuenta_naturales: true` se suma en T020 (Pulido), cuando el loader lo conozca;
  - el alta en el catálogo;
  - los tests de la 003 que leen el YAML real, actualizados según D10.

  La suite de contrato pasa con `[datos_gov_co_rues]` sin que se toquen sus tests. `test_todo_adaptador_de_registro_esta_declarado` y `test_todo_adaptador_de_registro_recibe_registro_costos` siguen en verde. T038 y T043 pasan a verde.

**Checkpoint**: la suite completa de `unit/`, `contratos/`, `arquitectura/` e `integration/` está en verde con la fuente conectada.

### Fase 7: Corrida real y cierre (Pasos 10 y 11)

- [ ] T050 [MIN] [Paso 10] **Una corrida real, avisada antes:** `uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11`, contra Postgres de desarrollo y sin token. *[MIN dudosa: las fixtures son sintéticas, y es la única prueba de que la API real devuelve leads.]*
  - Se anotan solo conteos en el PR: los segundos por request, las filas, los descartados y el `as_of`. Además, de 20 razones sociales al azar, cuántas parecen un nombre propio sin forma societaria. Si aparece alguna, se para.
  - **La respuesta no se commitea.**
  - Si la forma difiere de la fixture, se corrige la fixture y se vuelve a la Fase 5.
- [ ] T051 [MIN] [P] [Paso 11] `docs/arquitectura-backend.md`: 5 líneas, cómo conectar o desconectar una fuente, con este adaptador como ejemplo, y por qué la natural se filtra en el servidor. *[MIN: el doc va en el mismo cambio. La versión completa es T056.]*
- [ ] T053 [MIN] [Paso 11] Cierre:
  - la suite completa y `lint-imports` en verde;
  - el agente `security` sobre el diff (OWASP y principios V a VII), donde CRITICAL o HIGH bloquean;
  - commits convencionales, `feat(011): …`.

---

## Fase Pulido

Va después del mínimo, en este orden. Cada Rojo sigue siendo rojo real.

### Sin red (Paso 3)

*Las tests del mínimo inyectan `MockTransport`, así que ninguna sale a la red. Esto es la red de seguridad.*

- [ ] T009 [Paso 3] Stubs:
  - `backend/tests/_sin_red.py`, con `class RedBloqueadaEnTests(OSError)` y una fixture `sin_red` que todavía no parchea nada;
  - un `conftest.py` en `tests/unit/` y otro en `tests/contratos/`, que la importan como `autouse`.
- [ ] T010 [Paso 3] **Rojo:** `backend/tests/unit/test_sin_red.py`.
  - `::test_conexion_saliente_falla`, con `pytest.raises(RedBloqueadaEnTests)` alrededor de `socket.create_connection(("192.0.2.1", 443), timeout=0.5)`. Falla por aserción: sale `TimeoutError` u `OSError`, que no es `RedBloqueadaEnTests`.
  - `::test_loopback_sigue_permitido`. Es la guarda y nace verde.
- [ ] T011 [Paso 3] **Verde:** el parche de `socket.socket.connect` y `connect_ex` en `_sin_red.py`, como dice el plan, en "Diseño".
  - **Mutación:** bloquear loopback tiene que poner `test_loopback_sigue_permitido` en rojo. Se revierte.
  - Después se corren `uv run pytest -q tests/unit tests/contratos` completos, sin regresiones.

### Cámaras completas (Paso 2)

- [ ] T054 [Paso 2] **Rojo:** `test_camaras_co.py::test_yaml_real_cubre_58_camaras_y_33_departamentos`. Falla por aserción: hay 4 cámaras. **Verde:** las 58. Las `[VALIDAR]` se confirman con **una** consulta `$select=codigo_camara,camara_comercio&$group=codigo_camara,camara_comercio`, avisada antes y sin token, y con el sitio de Confecámaras. Solo se anotan los códigos en el YAML.

### Conteo de naturales (Paso 5), bloqueada por D2 y D3

- [ ] T019 [Paso 5] **Rojo:** `backend/tests/contratos/test_fuente_descubrimiento.py::test_campos_aditivos_del_resultado`. Parametrizado sobre **todo** el catálogo (Croma, OSM y datos.gov.co).
  - Lee `getattr(pagina, "descartados_no_juridica", None)`, `getattr(pagina, "naturales_no_descargadas", ...)` y `getattr(meta, "cuenta_naturales", None)`, y afirma tipos y combinaciones.
  - Falla por aserción: `None` no es `int`.
- [ ] T020 [Paso 5] **Verde:** en `descubrimiento/dominio/`, los campos aditivos con default:
  - `PaginaEmpresas.descartados_no_juridica: int = 0`;
  - `PaginaEmpresas.naturales_no_descargadas: int | None = None`;
  - `MetaFuente.cuenta_naturales: bool = False`, leído del YAML. El loader le da default `False` si la entrada no lo declara. `fuentes.yaml` suma `cuenta_naturales: true` en `datos_gov_co_rues`.
  - Croma y OSM no cambian.
- [ ] T021 [Paso 5] **Rojo:**
  - `::test_conteo_de_naturales_sin_filas`: la segunda request con `count(*)` y el `$where` de naturales sin `nit IS NOT NULL`, más `== 26304`.
  - `::test_conteo_de_naturales_falla_y_las_filas_siguen`: el conteo da dos 503, las empresas salen igual con `None`, y quedan 2 filas de costo del conteo.
  - En T015 se suma `descartados_no_juridica == 5`; en T029, la tercera fila (conteo a 1 s) y "0 requests de conteo" tras el fallo. Las tres son rojo real ahora.
- [ ] T022 [Paso 5] **Verde:** la request de conteo después de las filas, y el contador de descartes.

### Resto del adaptador (Paso 6)

- [ ] T026 [P] [Paso 6] **Rojo y verde:** `::test_cinco_mil_filas_marca_truncado`. Con 5.000 filas crudas y 3 descartables, `True`. Con 4.999, `False`. En los dos casos, `pagina.total is None` (D3): el total exacto lo da `contar`.
- [ ] T031 [Paso 6] **Rojo (D5):** tres tests de caché, con el caché en memoria de las fábricas de la 002.
  - `::test_cache_hit_no_hace_request`
  - `::test_conteo_fallido_no_se_cachea`: hace 1 request en el segundo `buscar`.
  - `::test_cache_no_guarda_lo_descartado`: lee la columna de D5.
- [ ] T032 [Paso 6] **Verde:** las dos claves (`filas` y `naturales`) con el discriminador dentro del hash. `contar` no se cachea en la 011: la 005 suma su clave junto con su test de hit de caché (YAGNI). Se guardan las filas ya filtradas, y un `None` no se cachea.
- [ ] T033 [Paso 6] **Rojo (D9):**
  - `::test_app_token_va_en_header_y_nunca_en_logs`. La parte del header es rojo real. Las de "nunca en logs" y "`tok-falso-123` no aparece en ningún `empresa.url_origen`" son guardas: la mutación `logger.debug(headers)`, o meter el token en la query de `url_origen`, las pone en rojo y se revierte.
  - `::test_url_se_puede_sobrescribir`.
- [ ] T034 [Paso 6] **Verde:** campos `datos_gov_co_url` y `datos_gov_co_app_token` en `settings` (sin literales: el default de la URL es la constante pública del dataset). La fábrica se los pasa al adaptador. *(En el mínimo no hay token, así que no hay secreto que manejar.)*
- [ ] T035 [Paso 6] **Rojo y verde de `contar` (D7):** son dos tests en `test_datos_gov_co.py`, y los dos tienen que fallar por aserción. Ni `xfail`, ni `ImportError`, ni `AttributeError`. *(Pulido: `contar` lo usa la vista previa de la 005, que no está en el mínimo.)*
  - **Antes del rojo**, se agrega el stub `DatosGovCoRues.contar(criterios) -> int`, que devuelve `0` sin hacer request ni registrar costo. Así el test encuentra el método y falla en el `assert`. El método es del adaptador, y el puerto no tiene que declararlo todavía.
  - `::test_contar_usa_count_con_el_mismo_where`.
    - El `$where` capturado se compara contra el literal de la spec (`test_query_filtra_juridicas_en_servidor`, spec.md:81): `organizacion_juridica != 'PERSONA NATURAL'`, `organizacion_juridica IS NOT NULL`, `estado_matricula = 'ACTIVA'`, `cod_ciiu_act_econ_pri = '4711'`, `codigo_camara in('04')` y `nit IS NOT NULL`. **No** se compara contra el builder de filas: si se comparara, quitar `nit IS NOT NULL` cambiaría los dos lados y el test quedaría verde.
    - **Rojo:** con el stub, falla `len(capturadas) == 1`, porque no hubo request, y falla `== 2015`.
    - **Mutación que lo pone en rojo:** quitar `nit IS NOT NULL` del `$where` de `contar` (falla contra el literal), o devolver un valor fijo en lugar del `count`.
  - `::test_contar_registra_socrata_descarga`.
    - Con un reloj falso que avanza 2 s, afirma 1 fila `socrata_descarga` con `unidades == Decimal("2")`, `unidades * costo_unitario == 2 * computo_seg_usd` (`OperacionCosto` no tiene campo `monto`) y el `lote_id` que llega por el constructor.
    - **Rojo:** con el stub, hay 0 filas `socrata_descarga` en el `RegistroCostos` falso, y el assert de 1 fila falla.
    - **Mutación que lo pone en rojo:** no registrar la fila, o registrarla con `unidades=0`, que hace fallar `unidades == Decimal("2")` y el producto con `costo_unitario`.
  - **Verde:** `contar` hace `$select=count(*)` con el mismo `$where` de jurídicas y registra una fila `socrata_descarga` antes de devolver.

### Migración, `EjecutarBusqueda` y CLI (Paso 8), bloqueada por D8

- [ ] T041 [Paso 8] **Rojo:** `test_rls.py`, el parametrizado de `busquedas`, suma `naturales_por_fuente` al SELECT del assert. Falla por aserción: la columna no existe y el SELECT de prueba la exige; el test atrapa `UndefinedColumn` y lo convierte en `pytest.fail`.
- [ ] T042 [Paso 8] **Verde:** `supabase/migrations/NNNN_naturales_por_fuente.sql` (D8), escrita a mano:

  ```sql
  ALTER TABLE busquedas ADD COLUMN naturales_por_fuente jsonb NOT NULL DEFAULT '{}';
  ```

  La migración trae **solo** esa columna. `costos.tipo` no se toca. `scripts/migrar_local.sh` se corre dos veces y el drift check queda en verde.
- [ ] T055 [Paso 8] **Rojo:** los 2 tests de `test_conectar_desconectar.py` que salieron de T043. `test_naturales_se_guardan_como_conteo` es el rojo real: hoy `naturales_por_fuente` queda en `{}`. `test_mismo_nit_que_supersociedades_fusiona_por_regla_1` es guarda: si nace verde, se comprueba quitando la fila de `cumplimiento` original.
- [ ] T044 [Paso 8] **Verde:** `EjecutarBusqueda` guarda `{clave: naturales_no_descargadas}` solo para las fuentes con `meta.cuenta_naturales`.
- [ ] T045 [P] [Paso 8] **Rojo:** `test_cli.py::test_respeta_fuentes_yaml_del_entorno`. La parte con `FUENTES_YAML` es rojo real. La de "sin la variable carga el del repo" es una guarda.
- [ ] T046 [Paso 8] **Verde:** la CLI lee `FUENTES_YAML` (por defecto `config/fuentes.yaml`) e imprime `naturales (encontradas, no contactables)` y `descartados_no_juridica` por fuente. La API no lee esa variable.

### Doc completa (Paso 11)

- [ ] T056 [Paso 11] `docs/arquitectura-backend.md` completa: lo de T051 más el conteo de naturales y el caché.
- [ ] T052 [P] [Paso 11] Se revisa que `spec.md` siga alineada con el plan. D1 (`meta`), D5 (`respuesta`) y D7 (tests movidos a la 005) ya se corrigieron en los commits de docs.

---

## Movidos a specs/005 (D7)

T047, T048 y T049 salen de la 011. Estos 6 tests los absorbe la 005, en la rama `docs/005-plan`:

| ID original | Test |
|---|---|
| T035 | `test_datos_gov_co.py::test_costo_maximo_llamada` |
| T035 | Los 3 tests de `contar` de la suite de contrato de la 005 (`tests/contratos/test_fuente_descubrimiento.py`), corriendo con `[datos_gov_co_rues]` |
| T047 | `backend/tests/integration/test_api_busquedas.py::test_tablero_trae_naturales_por_fuente` |
| T048 | `frontend/src/tablero/Tablero.test.tsx::muestra_naturales_encontradas_no_contactables` |

T049, el verde del tablero (`GET /tablero/fuentes`, la columna y las claves de i18n en es y en), se va con ellos. En la 011, el conteo de naturales llega hasta `busquedas.naturales_por_fuente` y la CLI.

---

## Dependencias

- **Ya, sin la 002 ni la 003:** T003, T004, T005 y T006–T008, en paralelo entre sí (archivos distintos). T006 crea `descubrimiento/aplicacion/camaras.py` (el paquete ya vino vacío de la 002).
- **Puerta.** T001 bloquea toda tarea marcada [002] o [003], y todo lo que viene después de la Fase 3.
- **Adaptador.** La Fase 4 necesita la Fase 3, porque el adaptador usa cámaras. La Fase 5 sigue a la 4. Las dos tocan el mismo archivo de adaptador y el mismo `test_datos_gov_co.py`: van en serie, con un solo dueño.
- **En paralelo dentro del mínimo, sin pisarse:** T036 (`test_costos_repo.py`) con T038 (`test_registro.py`, `test_seleccion_fuentes.py`) y T039 (`fabricas.py`), una vez que T030 está en verde. T051 con T050.
- **Registro e integración.** T043 se escribe en rojo antes de T040, y T040 pone en verde T038 y T043 en un commit.
- **Pulido.** Empieza con el mínimo en `main` o, si hay tiempo, después de T053. T019–T022 tocan el adaptador y el dominio: no se hacen en paralelo con la Fase 5. T055 y T044 necesitan T041–T042.
- **Pasos con advisor.** T017, T029 y T036 no pasan al verde sin APRUEBA.

## Estrategia: primero que funcione, después pulimos

1. **Mínimo** (Fases 1 a 7, 31 tareas [MIN]): datos.gov.co devuelve leads jurídicos, guardados por tenant con `cumplimiento` y `costos`, conectables y desconectables por YAML. Los ve el tablero de la 005, que ya lista leads por tenant.
2. **Pulido** (22 tareas): sin red, 58 cámaras, conteo de naturales y su migración, truncado, caché, token, `contar`, `FUENTES_YAML` en la CLI y la doc completa.

**No se negocian, ni en el mínimo:** rojo real en cada [MIN], el filtro jurídico y su defensa (T013–T018), el costo por intento (T029, T030, T036 y T037), el contrato (T039 y T040), `habilitado: true` y su par deshabilitado (T040 y T043), el aislamiento por tenant y el rol `app_rt` (T036 y T043), y ningún secreto en el repo (en el mínimo no hay token).
