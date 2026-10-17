# Tasks: 011 — datos.gov.co (`c82u-588k`), segunda fuente de descubrimiento, con contrato

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Prerequisites**:
- La 002 y la 003 mergeadas en `main`, y `main` mergeado en esta rama (con merge, no rebase).
- Las preguntas D1 a D12 de `plan.md` respondidas. D7 está pendiente del dueño, y solo bloquea T035 y T047–T049.

> Formato de `/speckit-tasks` aplicado a mano: `setup-plan.sh` no resuelve el feature.

**Formato**: `- [ ] TNNN [P?] [Paso n] Descripción`
- **[P]**: se puede hacer en paralelo, porque toca otro archivo y no depende de una tarea abierta.
- **[Paso n]**: el paso del "Plan de tareas" de la spec.
- **Rojo real.** Cada **Rojo** se corre y tiene que fallar **por aserción**. Un `ImportError`, un `AttributeError` o un `NotImplementedError` no cuentan. Por eso los stubs existen antes que su test, y los campos nuevos se leen con `getattr(x, "campo", None)` en el primer rojo.
- **Guardas.** Una guarda que nace verde se comprueba **por mutación**: se rompe a mano la implementación, se ve el rojo y se revierte. El commit no lleva la mutación.
- **(advisor)**: el advisor revisa el test antes de pasar al Verde.
- **Bloqueada por Dn**: no se empieza hasta que la pregunta n de `plan.md` esté resuelta.

Comando de la suite: `cd backend && uv run pytest -q && uv run lint-imports`. Para el front: `cd frontend && npm test`.

---

## Fase 1: Setup y puerta

- [ ] T001 **Puerta (D12).**
  - La 002 y la 003 están en `main`.
  - `git fetch && git merge origin/main` en `feature/011-datos-gov-co`. Si hay conflictos, se para y se avisa.
  - Las respuestas a D1–D11 quedan anotadas en `plan.md`.
  - Ninguna otra tarea arranca sin esto.
- [ ] T002 Se confirma que `pyyaml` y `httpx` ya están en `[project].dependencies` (`pyyaml` lo agrega la 002). **No se toca `pyproject.toml`.** `uv run lint-imports` en verde.
- [ ] T003 [P] Fixtures sintéticas en `backend/tests/fixtures/datos_gov_co/`. Las tres usan el esquema real de `c82u-588k`, NITs ficticios con el formato `9\d{8}` y ninguna razón social real.
  - `filas.json`: empresas válidas con las 7 columnas del `$select`.
  - `filas_descartables.json`: las válidas más un caso de cada tipo, de (a) a (d), más (a'), una natural escrita `"Persona Natural "` (mayúsculas mezcladas y un espacio al final).
  - `conteo_naturales.json`, con `[{"count": "26304"}]`.

**Checkpoint**: la rama está al día con `main` y la suite de la 002 y la 003 está en verde sin cambios.

---

## Fase 2: Skills (Paso 1), sin bloqueo

- [ ] T004 [P] [Paso 1] Cambios en `.claude/skills/fuentes-publicas/SKILL.md`.
  - Línea 39, la fila de `datos_gov_co_rues`:
    - `c82u-588k`;
    - `filtros: [ciiu, departamento]`;
    - la condición de jurídica se aplica en el servidor sobre `organizacion_juridica`;
    - `trae: [nit, nombre, ciiu, ciudad_camara]`;
    - "conectado".
  - Línea 56: `tipo_titular` de datos.gov.co sale de `organizacion_juridica` y **no** de `clase_identificacion`, porque la clase NIT incluye naturales.
- [ ] T005 [P] [Paso 1] Cambios en `.claude/skills/cumplimiento-datos/SKILL.md`.
  - Regla 1: la misma corrección que en T004.
  - Regla 4: una nota de que una fuente que permite filtrar en el servidor cuenta las naturales en lugar de guardarlas.

---

## Fase 3: Cámaras (Paso 2), sin bloqueo

- [ ] T006 [Paso 2] Stub `backend/app/modulos/descubrimiento/aplicacion/camaras.py`, con `Camara(codigo, nombre, municipio_sede, departamentos)` y dos funciones:
  - `cargar_camaras(ruta) -> {}`;
  - `camaras_de(camaras, departamento) -> set()`.

  Y `backend/config/camaras_co.yaml` vacío (`{}`).
- [ ] T007 [Paso 2] **Rojo:** `backend/tests/unit/descubrimiento/test_camaras_co.py`. Falla por aserción: hay 0 cámaras y `set() != {"04"}`.
  - `::test_yaml_real_cubre_58_camaras_y_33_departamentos`
  - `::test_bogota_y_cundinamarca`
- [ ] T008 [Paso 2] **Verde:**
  - `camaras_co.yaml` con las 58 cámaras y su cargador.
  - Las `[VALIDAR]` se confirman con **una** consulta `$select=codigo_camara,camara_comercio&$group=codigo_camara,camara_comercio`, avisada antes y sin token, y con el sitio de Confecámaras. Solo se anotan los códigos en el YAML.

---

## Fase 4: Sin red (Paso 3), sin bloqueo

- [ ] T009 [Paso 3] Stubs:
  - `backend/tests/_sin_red.py`, con `class RedBloqueadaEnTests(OSError)` y una fixture `sin_red` que todavía no parchea nada;
  - un `conftest.py` en `tests/unit/` y otro en `tests/contratos/`, que la importan como `autouse`.
- [ ] T010 [Paso 3] **Rojo:** `backend/tests/unit/test_sin_red.py`.
  - `::test_conexion_saliente_falla`, con `pytest.raises(RedBloqueadaEnTests)` alrededor de `socket.create_connection(("192.0.2.1", 443), timeout=0.5)`. Falla por aserción: sale `TimeoutError` u `OSError`, que no es `RedBloqueadaEnTests`.
  - `::test_loopback_sigue_permitido`. Es la guarda y nace verde.
- [ ] T011 [Paso 3] **Verde:** el parche de `socket.socket.connect` y `connect_ex` en `_sin_red.py`, como dice el plan, en "Diseño".
  - **Mutación:** bloquear loopback tiene que poner `test_loopback_sigue_permitido` en rojo. Se revierte.
  - Después se corren `uv run pytest -q tests/unit tests/contratos` completos, sin regresiones.

**Checkpoint**: `unit/` y `contratos/` corren sin red.

---

## Fase 5: Filtro jurídico (Paso 4), bloqueada por D1, D9 y (advisor)

- [ ] T012 [Paso 4] Stub del adaptador en `infraestructura/adaptadores/datos_gov_co_rues.py`.
  - Clase `DatosGovCoRues` con el constructor del plan: transporte, reloj, dormir, `RegistroCostos`, caché, cámaras, tarifas, `lote_id`, meta, `url` y `app_token`.
  - `buscar` devuelve `PaginaEmpresas` vacía y no hace requests.
  - **Todavía no** entra al catálogo: eso es T040.
- [ ] T013 [Paso 4] **Rojo (advisor):** `backend/tests/unit/descubrimiento/test_datos_gov_co.py::test_query_filtra_juridicas_en_servidor`.
  - Arranca con `assert len(capturadas) == 1`, antes de indexar, para que el rojo sea una aserción y no un `IndexError`.
  - Después toma la request de filas y afirma cada cláusula del `$where` de la spec, `$limit=5000` y que no haya `$order`, `$offset` ni `$group`.
  - Falla por aserción en el `len`: hay 0 requests capturadas.
- [ ] T014 [Paso 4] **Rojo (advisor):** `::test_select_no_pide_columnas_de_personas`.
  - `$select` igual a la lista exacta de 7 columnas.
  - Un `for` sobre las 8 columnas prohibidas, enumeradas en el test, que afirma que ninguna está.
- [ ] T015 [Paso 4] **Rojo (advisor):** `::test_cliente_descarta_lo_que_no_debio_llegar`, con `filas_descartables.json`.
  - Ningún `id_fiscal` ni `nombre` de los casos (a), (a'), (b), (c) ni (d) aparece en `empresas`.
  - La cantidad de empresas es igual a la cantidad de válidas.
  - El assert de `descartados_no_juridica == 5` se suma en T021, cuando el campo exista.
- [ ] T016 [Paso 4] **Guarda (advisor):** `::test_descartados_no_se_loguean`.
  - `caplog.set_level(DEBUG)` sobre el root, que incluye `httpx`. Ningún `record.getMessage()` ni `record.args` contiene el `nit` ni la `razon_social` de (a), (a') a (d).
  - **Mutación:** un `logger.debug(fila)` en el descarte → rojo. Se revierte.
- [ ] T017 [Paso 4] **Advisor:** revisa T013–T016 antes del verde. Sus hallazgos se aplican y se vuelve a pedir revisión hasta APRUEBA.
- [ ] T018 [Paso 4] **Verde:**
  - armado del SoQL desde criterios ya validados;
  - `_es_juridica_valida(fila)` pura, que en (a) compara con `strip().upper()`;
  - mapeo mínimo para que las válidas salgan.

**Checkpoint**: el principio VII queda cubierto en las dos capas.

---

## Fase 6: Conteo de naturales (Paso 5), bloqueada por D2 y D3

- [ ] T019 [Paso 5] **Rojo:** `backend/tests/contratos/test_fuente_descubrimiento.py::test_campos_aditivos_del_resultado`. Parametrizado sobre **todo** el catálogo (Croma y OSM hoy).
  - Lee `getattr(pagina, "descartados_no_juridica", None)`, `getattr(pagina, "naturales_no_descargadas", ...)` y `getattr(meta, "cuenta_naturales", None)`, y afirma tipos y combinaciones.
  - Falla por aserción: `None` no es `int`.
- [ ] T020 [Paso 5] **Verde:** en `descubrimiento/dominio/`, los campos aditivos con default:
  - `PaginaEmpresas.descartados_no_juridica: int = 0`;
  - `PaginaEmpresas.naturales_no_descargadas: int | None = None`;
  - `MetaFuente.cuenta_naturales: bool = False`, con su origen según D2 (si va en el YAML, el loader le da default `False`).
  - Croma y OSM no cambian.
- [ ] T021 [Paso 5] **Rojo:**
  - `::test_conteo_de_naturales_sin_filas`: la segunda request con `count(*)` y el `$where` de naturales sin `nit IS NOT NULL`, más `== 26304`.
  - `::test_conteo_de_naturales_falla_y_las_filas_siguen`: el conteo da dos 503, las empresas salen igual con `None`, y quedan 2 filas de costo del conteo. Con un `RegistroCostos` en memoria, porque las filas de costo se cierran en T030.
  - En T015 se suma `descartados_no_juridica == 5`, que ahora es rojo real.
- [ ] T022 [Paso 5] **Verde:** la request de conteo después de las filas, y el contador de descartes.

---

## Fase 7: Resto del adaptador (Paso 6), bloqueada por D4, D5, D9 y (advisor) en costos

- [ ] T023 [P] [Paso 6] **Rojo:** `::test_departamento_se_traduce_a_camaras`.
  - 25 → `in('04','14','47','58')`.
  - Un departamento fuera del YAML y el CIIU `"47' OR '1'='1"` → `CriterioNoSoportado` y 0 requests.
  - Si el caso 11 → `'04'` ya pasa por T018, se comprueba por mutación.
- [ ] T024 [P] [Paso 6] **Rojo:** `::test_mapea_fila_a_empresa_cruda`. Afirma los campos de la spec que existan en `EmpresaCruda` después de la 003, más `adaptador.meta.licencia == "CC-BY-SA-4.0"`. La licencia va en `meta`, no en `EmpresaCruda` (D4).
- [ ] T025 [P] [Paso 6] **Rojo:** `::test_as_of_sale_del_header`, con el header y sin él (reloj inyectable).
- [ ] T026 [P] [Paso 6] **Rojo:** `::test_cinco_mil_filas_marca_truncado`. Con 5.000 filas crudas y 3 descartables, `True`. Con 4.999, `False`. En los dos casos, `pagina.total is None` (D3): el total exacto lo da `contar`.
- [ ] T027 [P] [Paso 6] **Rojo:** `::test_pagina_2_vacia_sin_request`. Afirma 0 requests y 0 filas de costo.
- [ ] T028 [Paso 6] **Verde** de T023 a T027.
- [ ] T029 [Paso 6] **Rojo (advisor):** dos tests de costos.
  - `::test_registra_segundos_de_cada_intento`, con 503 → 200 en filas a 2 s y 3 s, y el conteo a 1 s. Quedan 3 filas `socrata_descarga` con `unidades` 2, 3 y 1, `Decimal(str(computo_seg_usd))`, `proveedor="datos.gov.co"`, `gratis=False`, `lead_id=None` y el `lote_id`.
  - `::test_segundo_fallo_lanza_fuente_no_disponible`: dos 503 (y la variante con dos `httpx.TimeoutException`) dan `FuenteNoDisponible`, 2 filas, 0 requests de conteo, y un `str(exc)` que no contiene el cuerpo de la respuesta (un marcador `"CUERPO-SECRETO"`).
  - El advisor revisa antes del verde, hasta APRUEBA.
- [ ] T030 [Paso 6] **Verde:** el bucle de 2 intentos.
  - Registra la fila **antes** de decidir.
  - La espera pasa por `dormir`, que no se mide.
  - `FuenteNoDisponible` lleva solo el status.
- [ ] T031 [Paso 6] **Rojo (D5):** tres tests de caché, con el caché en memoria de las fábricas de la 002.
  - `::test_cache_hit_no_hace_request`
  - `::test_conteo_fallido_no_se_cachea`: hace 1 request en el segundo `buscar`.
  - `::test_cache_no_guarda_lo_descartado`: lee la columna de D5.
- [ ] T032 [Paso 6] **Verde:** las tres claves (`filas`, `naturales` y `contar`) con el discriminador dentro del hash. Se guardan las filas ya filtradas, y un `None` no se cachea.
- [ ] T033 [Paso 6] **Rojo (D9):**
  - `::test_app_token_va_en_header_y_nunca_en_logs`. La parte del header es rojo real. Las de "nunca en logs" y "`tok-falso-123` no aparece en ningún `empresa.url_origen`" son guardas: la mutación `logger.debug(headers)`, o meter el token en la query de `url_origen`, las pone en rojo y se revierte.
  - `::test_url_se_puede_sobrescribir`.
- [ ] T034 [Paso 6] **Verde:** campos `datos_gov_co_url` y `datos_gov_co_app_token` en `settings` (sin literales: el default de la URL es la constante pública del dataset). La fábrica se los pasa al adaptador.
- [ ] T035 [Paso 6] **Rojo y verde de `contar` (D7):**
  - `::test_contar_usa_count_con_el_mismo_where` y `::test_contar_registra_socrata_descarga` son rojo real. Su verde es `DatosGovCoRues.contar(criterios) -> int`, un método del adaptador que no necesita que el puerto lo declare todavía.
  - `::test_costo_maximo_llamada` y los 3 tests de `contar` de la suite de contrato de la 005 se escriben con `xfail(strict=True, reason="depende de 005")` si la 005 no está en `main`, según lo que se resuelva en D7.
- [ ] T036 [Paso 6] **Guarda (advisor):** `backend/tests/integration/test_costos_repo.py::test_socrata_descarga_escribe_fila_en_costos`, con `postgres_costos` real, rol `app_rt` y `SET LOCAL` del tenant.
  - Valida `unidades == Decimal(2)`, el `costo_unitario` como `numeric`, `gratis=false` y el `tenant_id`.
  - **Nace verde**, porque el CHECK de `costos.tipo` de la 002 ya incluye `socrata_descarga` (plan 002, línea 210) y el adaptador ya registra desde T030.
  - **Mutación:** registrar `unidades` como `float` (falla `== Decimal(2)`) o un `tipo` fuera del CHECK (falla la constraint) tiene que ponerlo en rojo. Se revierte.
- [ ] T037 [Paso 6] El advisor revisa la guarda T036 y su mutación, hasta APRUEBA. No hay código nuevo.

**Checkpoint**: `test_datos_gov_co.py` y `test_costos_repo.py` en verde. Lo que dependa de la 005 queda en xfail.

---

## Fase 8: Registro y contrato (Paso 7), bloqueada por D10

- [ ] T038 [Paso 7] **Rojo:** dos tests, uno real y uno que puede nacer verde.
  - `test_registro.py::test_carga_config_fuentes_yaml_real_sin_error` se invierte: `datos_gov_co_rues` se carga, no está en `sin_implementacion`, y su entrada tiene `dataset == "c82u-588k"`, `filtros == ["ciiu", "departamento"]` y `licencia == "CC-BY-SA-4.0"`. Rojo real, porque hoy está en `false` con `nb3d-v3n7`.
  - `test_seleccion_fuentes.py::test_datos_gov_co_habilitada_recibe_ciiu_y_departamento`, con un registro en memoria. Si nace verde, porque la 003 ya trata `departamento` como geografía, se comprueba por mutación quitando `departamento` de los filtros, lo que da `sin_geografia`.
- [ ] T039 [P] [Paso 7] Fábrica `datos_gov_co_rues` en `backend/tests/contratos/fabricas.py`, con `MockTransport`, `filas.json` y `conteo_naturales.json`.
- [ ] T040 [Paso 7] **Verde, en UN commit:**
  - `fuentes.yaml` con `habilitado: true`, `dataset: c82u-588k`, `filtros: [ciiu, departamento]` y `trae: [nit, nombre, ciiu, ciudad_camara]` (más `cuenta_naturales: true` si así lo resuelve D2);
  - el alta en el catálogo;
  - los tests de la 003 y la 005 que leen el YAML real, actualizados según D10.

  La suite de contrato pasa con `[datos_gov_co_rues]` sin que se toquen sus tests. `test_todo_adaptador_de_registro_esta_declarado` y `test_todo_adaptador_de_registro_recibe_registro_costos` siguen en verde.

**Checkpoint**: la suite completa de `unit/`, `contratos/` y `arquitectura/` está en verde con la fuente conectada.

---

## Fase 9: Migración, `EjecutarBusqueda`, CLI e integración (Paso 8), bloqueada por D8 y D11

- [ ] T041 [Paso 8] **Rojo:** `test_rls.py`, el parametrizado de `busquedas`, suma `naturales_por_fuente` al SELECT del assert. Falla por aserción: la columna no existe y el SELECT de prueba la exige; el test atrapa `UndefinedColumn` y lo convierte en `pytest.fail`.
- [ ] T042 [Paso 8] **Verde:** `supabase/migrations/NNNN_naturales_por_fuente.sql` (D8), escrita a mano:

  ```sql
  ALTER TABLE busquedas ADD COLUMN naturales_por_fuente jsonb NOT NULL DEFAULT '{}';
  ```

  La migración trae **solo** esa columna. `costos.tipo` no se toca. `scripts/migrar_local.sh` se corre dos veces y el drift check queda en verde.
- [ ] T043 [Paso 8] **Rojo (D11):** `backend/tests/integration/test_conectar_desconectar.py`, los 5 tests de la spec. `test_naturales_se_guardan_como_conteo` es el rojo real: hoy `naturales_por_fuente` queda en `{}`. Los otros 4 se comprueban por mutación si nacen verdes, poniendo `habilitado: false` en el YAML real o quitando la fila de `cumplimiento`.
- [ ] T044 [Paso 8] **Verde:** `EjecutarBusqueda` guarda `{clave: naturales_no_descargadas}` solo para las fuentes con `meta.cuenta_naturales`.
- [ ] T045 [P] [Paso 8] **Rojo:** `test_cli.py::test_respeta_fuentes_yaml_del_entorno`. La parte con `FUENTES_YAML` es rojo real. La de "sin la variable carga el del repo" es una guarda.
- [ ] T046 [Paso 8] **Verde:** la CLI lee `FUENTES_YAML` (por defecto `config/fuentes.yaml`) e imprime `naturales (encontradas, no contactables)` y `descartados_no_juridica` por fuente. La API no lee esa variable.

**Checkpoint**: la integración está en verde contra Postgres de prueba.

---

## Fase 10: Tablero (Paso 9), bloqueada por D6 y D7

- [ ] T047 [Paso 9] **Rojo:** `backend/tests/integration/test_api_busquedas.py::test_tablero_trae_naturales_por_fuente`.
  - Con la 005 en `main`, es un rojo real.
  - Sin la 005, se escribe con `xfail(strict=True)`.
- [ ] T048 [P] [Paso 9] **Rojo:** `frontend/src/tablero/Tablero.test.tsx::muestra_naturales_encontradas_no_contactables`.
  - Tres casos: `26.304`, `—` y "no aplica".
  - Las cadenas salen de i18n en es y en, y el test corre en los dos idiomas.
  - Sin la 005, va con `it.fails`.
- [ ] T049 [Paso 9] **Verde:**
  - `GET /tablero/fuentes`, con `DISTINCT ON (fuente) … ORDER BY creada_en DESC` sobre las búsquedas completadas;
  - la columna del tablero y las claves de i18n en es y en.

  Solo si la 005 está en `main`. Si no, se pasa a la 005.

---

## Fase 11: Corrida real (Paso 10)

- [ ] T050 [Paso 10] **Una corrida real, avisada antes:** `uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11`, contra Postgres de desarrollo y sin token.
  - Se anotan solo conteos en el PR: los segundos por request, las filas, los descartados, las naturales y el `as_of`. Además, de 20 razones sociales al azar, cuántas parecen un nombre propio sin forma societaria. Si aparece alguna, se para.
  - **La respuesta no se commitea.**
  - Si la forma difiere de la fixture, se corrige la fixture y se vuelve a la Fase 7.

---

## Fase 12: Doc y cierre (Paso 11)

- [ ] T051 [Paso 11] `docs/arquitectura-backend.md`: cómo conectar o desconectar una fuente, con este adaptador como ejemplo, y por qué la natural se filtra en el servidor y se cuenta. El mínimo si se corta son 5 líneas.
- [ ] T052 [P] [Paso 11] Se revisa que `spec.md` siga alineada con el plan. D1 (`meta`) y D5 (`respuesta`) ya se corrigieron en el commit de docs; D7 se aplica cuando el dueño decida.
- [ ] T053 [Paso 11] Cierre:
  - la suite completa, `lint-imports` y `npm test` en verde;
  - el agente `security` sobre el diff (OWASP y principios V a VII), donde CRITICAL o HIGH bloquean;
  - commits convencionales, `feat(011): …`.

---

## Dependencias

- **Puerta.** T001 bloquea todo lo demás, salvo T004 y T005.
- **Independientes entre sí.** Las Fases 2, 3 y 4 no dependen una de otra.
- **Adaptador.** La Fase 5 necesita las Fases 3 y 4, porque el adaptador usa cámaras y los tests corren sin red. Las Fases 6 y 7 siguen a la 5.
- **Registro.** La Fase 8 necesita las Fases 5 a 7 en verde, porque `habilitado: true` va en el mismo commit en que pasa el contrato.
- **Integración.** La Fase 9 necesita la Fase 8.
- **Tablero.** La Fase 10 necesita la Fase 9 y la 005.
- **Antes de la doc.** La Fase 11 va antes de la Fase 12.
- **Pasos con advisor.** T017, T029 y T036 no pasan al verde sin APRUEBA.

## Cuándo cortar (de la spec, en este orden)

| Orden | Se corta | Tareas que se bajan |
|---|---|---|
| 1 | Doc completa | T051 queda en 5 líneas |
| 2 | Columna de naturales en el tablero | T047, T048 y T049 |
| 3 | `FUENTES_YAML` en la CLI | T045. T046 queda solo con la impresión |
| 4 | Las 58 cámaras | `test_yaml_real_cubre_58…` de T007. T008 queda con las cámaras 04, 14, 47 y 58 |
| 5 | Caché | T031 y T032 |

**No se cortan:**
- el filtro jurídico y su defensa (T013–T018);
- el conteo en `busquedas` (T021, T022, T043 y T044);
- el contrato (T019, T020 y T038–T040);
- `habilitado: true` y su par deshabilitado (T040 y T043);
- la fixture sin red (T009–T011);
- el costo por intento (T029, T030, T036 y T037);
- el token fuera de los logs (T033 y T034);
- `cumplimiento` con CC BY-SA (T043).
