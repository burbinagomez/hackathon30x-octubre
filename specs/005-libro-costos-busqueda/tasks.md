# Tasks: 005 — Libro de costos, CPL por fuente y "Nueva búsqueda"

**Input**: `spec.md` y `plan.md` de esta carpeta.

**Formato**: `- [ ] TNNN [P?] [Paso n] descripción con ruta`.
- **Rojo** = test que falla **por aserción**. Nunca `xfail` plano, `ImportError` ni `AttributeError`: antes de cada rojo va un esqueleto que importa y devuelve un valor equivocado.
- **Mutación** = el cambio de una línea en el código que tiene que poner ese test en rojo. Si un test nace verde, se acepta solo si su mutación lo pone en rojo; la mutación se aplica, se ve el rojo y se revierte.
- **Decimal**: todo monto se asierta con `type(v) is Decimal` y contra `Decimal("…")` construido desde string. Con una mutación float, `2.0 == Decimal(2)` da `True` y no hay rojo; por eso los esperados no son enteros y se chequea el tipo.
- **(advisor)** / **(security)**: el test lo revisa ese agente **antes** de aceptarlo. Cubre costos, fórmulas CPL/CPQL, cumplimiento y RLS.
- **viene de 011 (D7)**: test movido desde la 011, con el mismo nombre (ver Fase 4, Fase 8 y Fase 9).

## Fase 1: Puerta y setup

- [ ] T001 [Paso 0] **Puerta.** `git fetch origin`. Confirmar que 002, 003, 011 y 004 están en `main`. Elegir el número de migración: el siguiente libre en `supabase/migrations/` (P5). Si las preguntas P1–P4 y P6 no tienen respuesta del dueño, frenar.
- [ ] T002 [P] [Paso 0] `backend/pyproject.toml` suma `PyJWT`. `uv lock`.
- [ ] T003 [P] [Paso 0] `frontend/package.json` suma `react-i18next` e `i18next` como dependencias, y `eslint`, `typescript-eslint`, `eslint-plugin-boundaries`, `eslint-plugin-import`, `eslint-import-resolver-typescript` y `eslint-plugin-i18next` como devDependencies.
- [ ] T004 [Paso 0] **Esqueletos.** Las firmas del plan, que devuelven valores equivocados para que los rojos sean por aserción:
  - `contar` → `-1`;
  - `gasto_busqueda` → `Decimal("-1")`;
  - `costo_maximo_llamada = Decimal("0")`;
  - `filtrar_por_palabras` → `[]`;
  - `VistaPrevia` y `EjecutarBusqueda` → resultados vacíos;
  - los routers registrados, que devuelven `501`.

## Fase 2: Migración y vistas (Paso 1)

- [ ] T005 [Paso 1] **Esqueleto de la migración** `supabase/migrations/NNNN_libro_costos_busqueda.sql`:
  - columnas, `usuarios`, funciones e índices de plan §Migración;
  - las 9 vistas con sus columnas finales, `WHERE false` y **sin** `security_invoker`.

  `app/modelos.py` se actualiza a la par.
- [ ] T006 [Paso 1] `backend/tests/arquitectura/test_migraciones.py::test_migrar_local_desde_vacio_dos_veces_sin_drift` (de la 002) sigue verde con la migración nueva. Se confirma que `compare_metadata` no reporta las vistas. **Mutación:** borrar `fusionado_en` de `modelos.py` → drift.
- [ ] T007 [Paso 1] **Rojo (advisor):** `backend/tests/integration/test_vistas_costos.py`, con el fixture de spec:77-112, sembrado con `postgres` y leído como `app_rt`. Cada test, con su mutación:
  - `::test_cpl_por_fuente_fixture_10_leads`: la tabla exacta, con `type is Decimal`. **Mutación:** `unicos = count(*)` en lugar de `count(DISTINCT lead_id)` → osm 8 ≠ 7. **Segunda mutación:** `::float8` en `cpl_lista` → rojo por el tipo.
  - `::test_costo_por_lead_conserva_el_total`. **Mutación:** `v_costo_por_lead` sin el costo directo (`lead_id IS NOT NULL`) → Σ cs se queda corto por 0.05.
  - `::test_lote_sin_leads_es_desperdicio`. **Mutación:** `v_prorrateo` agrupa por `fuente_ef` sin `lote_id` → la fila 5 se reparte entre los leads de L1.
  - `::test_prorrateo_es_por_lote_y_fuente`: osm L2 = `Decimal("0.16")`. **Mutación:** dividir por los leads de la fuente en todos los lotes (7) → 0.80/7.
  - `::test_lead_de_dos_fuentes_cuenta_una_vez_en_total`. **Mutación:** `TOTAL.unicos = SUM(unicos)` → 11.
  - `::test_evals_excluido_y_aparte`. **Mutación:** quitar `fuente IS DISTINCT FROM 'evals'` de `v_costos` → TOTAL 3.82.
  - `::test_fuente_nula_es_sin_atribuir`. **Mutación:** `fuente <> 'evals'` en lugar de `IS DISTINCT FROM` → la fila 4 (NULL) desaparece.
  - `::test_divisor_cero_es_null`: `is None`. **Mutación:** `COALESCE(… / NULLIF(icp,0), 0)` → `Decimal("0")`.
  - `::test_costo_por_canal`: email 0.05 y whatsapp 0.30. **Mutación:** sin `WHERE canal IS NOT NULL` → aparece una fila `None`.
  - `::test_fila_con_lote_y_lead_va_al_lead`: B = 0.25/0.15 y Σ parte (L1, cs) = 0.80/0.40. **Mutación:** el prorrateo filtra `lote_id IS NOT NULL` en lugar de `lead_id IS NULL` → Σ parte 0.85.
  - `::test_lead_fusionado_no_cuenta`: únicos 6, encontrados 7, prorrateo L2 `Decimal("0.20")`. **Mutación:** `v_leads_icp` sin `fusionado_en IS NULL` → 7 y 0.16.
- [ ] T008 [Paso 1] **Verde:** las 9 vistas de spec:313-335, con `security_invoker = true` y `GRANT SELECT` a `app_rt`, y el `CHECK` de `estado` (P1).
- [ ] T009 [Paso 1] **Rojo (advisor, RLS):** `backend/tests/integration/test_rls.py`:
  - `::test_tenant_b_no_accede_a_datos_de_a[vista]`, sobre cada `v_*`: control positivo de A ≥ 1 fila, B ve 0 filas y 0 filas `TOTAL`. La siembra de A trae una `lead_fuentes` de `osm_overpass`. Rojo hoy: las vistas sin `security_invoker` corren como `postgres`. **Mutación tras el verde:** quitar `security_invoker` de una vista, o quitar `HAVING count(*) > 0` → B ve una fila `TOTAL`.
  - `::test_toda_vista_es_security_invoker`, desde `pg_class`. **Mutación:** una vista sin la opción.
  - `::test_usuarios_tiene_rls`. **Mutación:** sin `ENABLE ROW LEVEL SECURITY`, o sin la política.
- [ ] T010 [P] [Paso 1] **Rojo (advisor):** `backend/tests/integration/test_privilegios_supabase.py::test_anon_y_authenticated_sin_privilegios` (de la 002) suma `pg_views`, con el assert previo de que esté `v_tablero_fuentes`. **Mutación:** sacar `pg_views` de la unión (falla el assert previo), o `GRANT SELECT ON v_tablero_fuentes TO anon`.
- [ ] T011 [Paso 1] **Verde:** `security_invoker` en las 9 vistas y la RLS de `usuarios`.
- [ ] T012 [Paso 1] **Rojo (security, RLS):** `backend/tests/integration/test_usuarios_repo.py`:
  - `::test_app_rt_no_lee_usuarios_directo`. **Mutación:** `GRANT SELECT ON usuarios TO app_rt`.
  - `::test_usuario_para_login_devuelve_solo_ese_email`. **Mutación:** comparar `email = p_email` sin `lower()` → `A@X.co` devuelve 0 filas.
  - `::test_email_se_guarda_en_minusculas`: sqlstate `23514`. **Mutación:** sin el `CHECK`.
  - `::test_fijar_idioma_no_cruza_tenants`. **Mutación:** sin `AND tenant_id = current_setting(...)` → modifica 1 fila.
  - `::test_funcion_es_security_definer_con_search_path[usuario_para_login|fijar_idioma]`, con el `ALTER DEFAULT PRIVILEGES` en `supabase_simulado.sql`. **Mutación:** sin el `REVOKE` → `anon` tiene `EXECUTE`.
- [ ] T013 [Paso 1] **Verde:** las funciones, el `REVOKE`/`GRANT` y el `DO` con el guard de `pg_roles`. `backend/scripts/crear_usuario.py` con `getpass`.

**Checkpoint**: vistas, RLS, privilegios y usuarios verdes.

## Fase 3: `gasto_busqueda` y lote (Paso 2)

- [ ] T014 [Paso 2] **Rojo (advisor, costos):** `backend/tests/integration/test_costos_repo.py::test_gasto_busqueda_suma_lista_del_lote`, con montos no enteros (`0.40` gratis y `0.07`) y filas de otro lote; espera `Decimal("0.47")`. **Mutación:** sumar `monto_real` → 0.07, o sin el filtro de `lote_id` → incluye el otro lote.
- [ ] T015 [Paso 2] **Verde:** `postgres_costos.gasto_busqueda` y el método en el Protocol (P3), más el registro falso compartido de `tests/`.

## Fase 4: `contar()` y `costo_maximo_llamada` (Paso 3)

- [ ] T016 [Paso 3] **Rojo (advisor, costos):** `backend/tests/contratos/test_fuente_descubrimiento.py`, parametrizado sobre el catálogo (`croma_supersociedades_co`, `osm_overpass`, `datos_gov_co_rues`). Los tres tests:
  - `::test_contar_registra_costo_antes_de_devolver[…]`. Un caso con éxito y otro con transporte que siempre falla (sale `FuenteNoDisponible`): en los dos hay ≥ 1 fila en el registro falso. **Mutación:** `registrar` solo en el camino feliz.
  - `::test_contar_devuelve_entero_no_negativo_o_none[…]`: `type(r) is int and r >= 0` o `r is None`. **Mutación:** devolver el `total` crudo del JSON (`"2015"`, un str) → rojo por el tipo.
  - `::test_contar_rechaza_criterio_no_soportado[…]`: `CriterioNoSoportado` y 0 requests en el transporte. **Mutación:** validar después del request → 1 request.

  **viene de 011 (D7):** las tres parametrizaciones `[datos_gov_co_rues]` (T035 de la 011).
- [ ] T017 [P] [Paso 3] **Rojo:** `backend/tests/unit/descubrimiento/test_croma_supersociedades.py`:
  - `::test_contar_lee_total_de_la_pagina_1`, con la fixture sintética con `total=2015` y 100 ítems. **Mutación:** `len(empresas)` → 100.
  - `::test_contar_y_buscar_hacen_una_sola_request`: 1 request y 1 fila. **Mutación:** `contar` con `per_page=1` → otra clave de caché → 2 requests.
  - `::test_ingresos_min_se_envia_como_filtro`. **Mutación:** sacar `ingresos_min` del mapeo de parámetros.
  - `::test_costo_maximo_llamada`: `== Decimal("0.00099")` (1 × `usd_por_credito`). No está en la spec; lo suma el plan para que cs no quede sin test. **Mutación:** usar `creditos_live` (10) → 0.0099.
- [ ] T018 [P] [Paso 3] **Rojo:** `backend/tests/unit/descubrimiento/test_osm_overpass.py`:
  - `::test_contar_usa_out_count`: el body trae `out count;` y no `out center tags`, y lee `int(elements[0].tags.total)`. **Mutación:** reusar la query de `buscar`.
  - `::test_contar_registra_segundos`, con reloj falso y una espera de `Retry-After` de por medio: unidades = segundos del request. **Mutación:** medir desde antes de la espera → incluye los segundos de `sleep`.
  - `::test_costo_maximo_llamada`: `== Decimal("0.00042")` (2 × 30 × 0.0000070). No está en la spec; lo suma el plan. **Mutación:** 1 intento → 0.00021.
- [ ] T019 [P] [Paso 3] **Rojo (advisor, costos):** `backend/tests/unit/descubrimiento/test_datos_gov_co.py`:
  - `::test_costo_maximo_llamada`: `meta.costo_maximo_llamada == Decimal("0.00084")`, que es 2 requests × 2 intentos × 30 s × `computo_seg_usd`, con `type is Decimal`. La fórmula está en la 011 spec (f8f9456):230. **viene de 011 (D7)** (T035 de la 011). **Mutación:** 2 × 30 (sin las 2 requests) → 0.00042; o calcular con `float` → `0.0008399999…`, rojo por valor y por tipo.
  - `::test_contar_segunda_llamada_sale_del_cache`: dos `contar` con los mismos criterios dan 1 request y 1 fila de costo. Es nuevo en la 005 por el advisor de la 011: la 011 deja el discriminador en `tipo: filas|naturales`. **Rojo natural:** sin `tipo: contar`, `contar` no cachea → 2 requests. **Mutación tras el verde:** `contar` con el discriminador `filas` → choca con la clave de filas, y el test agrega un `buscar` previo con los mismos criterios para que la mutación dé rojo.
  - Los tests que quedan en la 011 (`test_contar_usa_count_con_el_mismo_where` y `test_contar_registra_socrata_descarga`) **no se duplican**.
- [ ] T020 [Paso 3] **Verde:**
  - `contar` en el Protocol y en los tres adaptadores;
  - `costo_maximo_llamada` calculado en cada fábrica (P4);
  - `tipo: contar` en el discriminador de caché de `datos_gov_co_rues`;
  - `CROMA_BASE_URL` en `Settings`.

**Checkpoint**: la suite de contrato, verde con los tres adaptadores.

## Fase 5: Selección y post-filtro (Paso 4)

- [ ] T021 [Paso 4a] **Caracterización:** `backend/tests/unit/descubrimiento/test_seleccion_fuentes.py::test_tamano_es_refinamiento_no_requisito` (archivo de la 003, ver P8). Puede nacer verde (P9). **Mutación:** en `seleccionar_fuentes`, descartar la fuente que no declara `ingresos_min` → OSM queda descartada. El advisor confirma.
- [ ] T022 [P] [Paso 4b] **Rojo:** `backend/tests/unit/descubrimiento/test_palabras_clave.py`:
  - `::test_coincide_por_token_normalizado`. **Mutación:** comparar sin `normalizar_nombre` → la tilde no matchea; o usar substring (`in`) → `"pan"` matchea `"panaderia"`.
  - `::test_exclusion_gana_sobre_palabra_clave`. **Mutación:** devolver `True` en cuanto matchea la palabra clave, antes de mirar las exclusiones.
  - `::test_palabra_clave_de_varios_tokens_exige_todos`. **Mutación:** `any` en lugar de `all`.
  - `::test_sin_palabras_ni_exclusiones_pasa_todo`. **Mutación:** `any([])` como condición → no pasa nada.
- [ ] T023 [Paso 4b] **Verde:** `descubrimiento/dominio/palabras_clave.py`, puro, con el normalizador de la 003.

## Fase 6: `VistaPrevia` y `EjecutarBusqueda` con tope (Paso 5) — advisor

- [ ] T024 [Paso 5] **Rojo (advisor, costos):** `backend/tests/unit/descubrimiento/test_vista_previa.py`, con fuentes, repo y libro falsos:
  - `::test_conteo_por_fuente_y_motivo_de_las_descartadas` (`pais=PE`). **Mutación:** no copiar `ignoradas` a la respuesta.
  - `::test_crea_busqueda_en_borrador_con_criterios`. **Mutación:** usar `crear_busqueda` del 002 → estado `creada`.
  - `::test_fuente_no_disponible_da_conteo_null_y_sigue`. **Mutación:** dejar que la excepción se propague → cs no tiene conteo.
  - `::test_limite_agotado_da_conteo_null`. **Mutación:** mapear todo error a `no_disponible`.
  - `::test_costo_estimado_suma_lo_gastado_y_lo_que_falta`: el gastado sale del libro falso (`Decimal("0.00113")`) + 0 de cs + segundos de OSM × 0.0000070. **Mutación:** sumar 1 crédito de cs aunque haya caché.
  - `::test_costo_maximo_suma_costo_maximo_llamada_de_cada_fuente`. Tres casos:
    - cs + OSM: gastado + 0.00099 + 0.00042;
    - cs + OSM + `datos_gov_co_rues`: + 0.00084 (el agregado del advisor de la 011);
    - borde: `dentro_del_tope` es `False` con un tope de un centavo menos y `True` con un tope igual al máximo.

    **Mutación:** iterar sobre un subconjunto fijo de claves (sin `datos_gov_co_rues`) → falla el segundo caso; o `<` en lugar de `≤` → falla el borde.
  - `::test_reporta_creditos_y_requests_restantes`: 63 y 288. **Mutación:** devolver lo usado en lugar de lo restante.
- [ ] T025 [Paso 5] **Verde:** `descubrimiento/aplicacion/vista_previa.py` y los métodos de borrador de `RepositorioLeads` (P2), con `ignorados` derivado (P7).
- [ ] T026 [Paso 5] **Rojo (advisor, costos y cumplimiento):** `backend/tests/unit/descubrimiento/test_ejecutar_con_tope.py`:
  - `::test_no_ejecuta_si_costo_maximo_supera_tope`: `TopeExcedido`, 0 requests, estado `borrador`. **Mutación:** chequear el tope después de `pasar_a_ejecutando`.
  - `::test_corta_antes_de_la_llamada_que_pasaria_el_tope`. **Mutación:** chequear después de llamar → OSM se llama.
  - `::test_solo_ejecuta_borrador`: `BusquedaYaEjecutada`. **Mutación:** ignorar el `bool` de `pasar_a_ejecutando`.
  - `::test_usa_los_criterios_guardados`, con un `assert` sobre `inspect.signature(ejecutar)`. **Mutación:** aceptar `criterios=None` y usarlo si viene.
  - `::test_filtradas_por_palabras_no_generan_lead_ni_cumplimiento`: el repo falso no recibe `obtener_o_crear_lead` para la filtrada, y el costo de la llamada sigue en el lote. **Mutación:** filtrar después de persistir.
- [ ] T027 [Paso 5] **Verde:** `EjecutarBusqueda` con tope, `lote_id = busqueda.id`, estado final (P1) y `naturales_por_fuente` (011).
- [ ] T028 [Paso 5] **Rojo (advisor, costos):** `backend/tests/integration/test_costos_repo.py::test_costos_de_descubrimiento_llevan_lote_de_la_busqueda` (spec:141), con transportes falsos y `postgres_costos` real. **Mutación:** construir los adaptadores de la vista previa con `lote_id=None`. Va acá y no en la Fase 3 porque necesita los dos casos de uso.

## Fase 7: Auth (Paso 6) — security

- [ ] T029 [Paso 6] **Rojo (security):** `backend/tests/integration/test_auth.py`:
  - `::test_sesion_con_clave_correcta_devuelve_token`. **Mutación:** `exp` de 8 min.
  - `::test_clave_incorrecta_y_email_inexistente_dan_el_mismo_401`, con un spy sobre `hashlib.scrypt` llamado en los dos casos. **Mutación:** `return 401` sin el scrypt de relleno.
  - `::test_sin_token_da_401[ruta]`, sobre `app.routes`. **Mutación:** una ruta sin la dependencia `tenant_actual`.
  - `::test_token_invalido_da_401[caso]`: vencido, otra clave, `alg=none`, sin `exp`, sin `tenant_id`. **Mutación:** sacar `require` → los casos sin `exp` y sin `tenant_id` pasan.
  - `::test_app_no_arranca_sin_session_secret`. **Mutación:** sin el validador de largo mínimo.
  - `::test_docs_desactivadas`. **Mutación:** `docs_url` por defecto.
  - `::test_cors_solo_permite_web_origin`. **Mutación:** `allow_origins=["*"]`.
  - `::test_clave_no_aparece_en_logs`. **Mutación:** `logger.info(body)`.
  - `::test_sesion_devuelve_idioma[caso]`. **Mutación:** `COALESCE(usuarios.idioma, tenants.idioma)` → `idioma_usuario` nunca es `null`.
  - `::test_fijar_idioma_persiste`. **Mutación:** devolver 204 sin llamar a `fijar_idioma`.
  - `::test_fijar_idioma_invalido_da_422[caso]`. **Mutación:** modelo sin `extra='forbid'`.
- [ ] T030 [Paso 6] **Verde:**
  - `acceso/dominio/claves.py` (scrypt con n=2¹⁷, r=8, p=1 y `maxmem=2²⁸`);
  - `repositorio_usuarios.py`;
  - `app/api/sesion.py`;
  - `/auth/sesion` y `PATCH /usuarios/me`;
  - `session_secret` y `web_origin` en `Settings`;
  - docs off y CORS.

## Fase 8: Endpoints (Paso 7)

- [ ] T031 [Paso 7] **Rojo:** `backend/tests/integration/test_api_busquedas.py`:
  - `::test_tenant_sale_del_token_no_del_body` (advisor, RLS). **Mutación:** modelo sin `extra='forbid'` → 201 en lugar de 422.
  - `::test_tenant_b_no_ejecuta_busqueda_de_a` (advisor, RLS). **Mutación:** abrir la unidad de trabajo con el tenant de la búsqueda en lugar del del token.
  - `::test_ejecutar_dos_veces_da_409`. **Mutación:** mapear `BusquedaYaEjecutada` a 500.
  - `::test_ejecutar_con_costo_maximo_sobre_tope_da_409` (advisor, costos): 0 filas nuevas en `costos`. **Mutación:** llamar `contar` de nuevo antes de chequear.
  - `::test_validacion[caso]`. **Mutación:** sin `le=TOPE_MAXIMO_USD`, o sin validar `canal_preferido` contra el YAML.
  - `::test_tablero_devuelve_null_para_cpl_sin_divisor`. **Mutación:** serializar `None` como `"0"`.
  - `::test_vista_previa_devuelve_motivos_como_codigo`. **Mutación:** devolver `msg` de pydantic.
  - `::test_actividades_trae_ambos_nombres`. **Mutación:** omitir la clave `nombre_en` cuando es `null`.
  - `::test_tablero_atribucion_solo_de_fuentes_presentes[caso]` (advisor, cumplimiento). **Mutación:** sin el `EXISTS` → `solo_croma` trae dos.
  - `::test_tablero_trae_naturales_por_fuente`. **viene de 011 (D7)** (T047 de la 011). Definición en la 011 spec (f8f9456):135. **Mutación:** `COALESCE(naturales, 0)` → OSM trae `0` en lugar de `null`; o `ORDER BY … ASC` → toma el conteo viejo.
- [ ] T032 [Paso 7] **Verde:**
  - routers `busquedas`, `tablero`, `actividades`;
  - `repositorio_tablero.py`;
  - `limites_app` en `tarifas.yaml` (P11);
  - `nombre_es`/`nombre_en` en `actividades.yaml`;
  - la columna de orden del tablero (P6);
  - el verde del tablero de naturales, `DISTINCT ON (fuente)` sobre las búsquedas `completada`. **viene de 011 (D7)** (T049 de la 011).
- [ ] T033 [Paso 7] `EXCLUIDOS` de los tests de arquitectura de la 002 suma `repositorio_tablero.py` y `repositorio_usuarios.py` (P10). `uv run lint-imports` verde.

## Fase 9: Front (Paso 8)

- [ ] T034 [Paso 8] Mover `src/setupTests.ts` a `src/test/setup.ts` y sumar `src/test/servidor.ts` (MSW sin handlers). `vitest.config.ts` incluye `src/**` y `tests/**` y excluye `e2e/`.
- [ ] T035 [Paso 8] **Rojo:** `frontend/tests/arquitectura/limites.test.ts`, los 6 tests de spec:221-235. **Mutación:** cada negativo, con su dirección en `allow`; para `import_sin_resolver_es_error`, `import/no-unresolved` en `off`.
- [ ] T036 [Paso 8] **Verde:** `frontend/eslint.config.js` (boundaries, en el orden de tipos de spec:445-452, más el resolver de TS).
- [ ] T037 [Paso 8] **Rojo:**
  - `frontend/tests/arquitectura/i18n.test.ts`, los 4 tests. **Mutación:** borrar una clave de `en.json`; `mode` que no atrapa atributos.
  - `frontend/src/i18n/elegirIdioma.test.ts::precedencia[caso]`. **Mutación:** el tenant antes que el navegador.
- [ ] T038 [Paso 8] **Verde:** `src/i18n/` y la regla `i18next/no-literal-string`.
- [ ] T039 [P] [Paso 8] **Rojo:**
  - `frontend/src/acceso/Login.test.tsx::selector_sin_sesion_no_guarda`. **Mutación:** `PATCH` sin mirar la sesión.
  - `frontend/src/api/cliente.test.ts::un_401_lleva_al_login_y_borra_el_token`. **Mutación:** no borrar el token.
- [ ] T040 [P] [Paso 8] **Rojo:** `frontend/src/busqueda/NuevaBusqueda.test.tsx`, los 6 tests de spec:251-257. **Mutación:** habilitar Buscar comparando el estimado en lugar del máximo; no invalidar la vista previa al cambiar un filtro.
- [ ] T041 [P] [Paso 8] **Rojo:** `frontend/src/tablero/Tablero.test.tsx`:
  - los 6 de spec:259-268. **Mutación:** formatear `null` como `0`; un texto de atribución hardcodeado.
  - `::muestra_naturales_encontradas_no_contactables`. **viene de 011 (D7)** (T048 de la 011). Tres casos, en es y en:
    - `26304` se muestra "26.304" en es y "26,304" en en, con el esperado calculado con `Intl.NumberFormat`;
    - `null` se muestra "—";
    - `cuenta_naturales: false` se muestra el texto i18n de "no aplica".

    **Mutación:** `valor ?? 0` → "0".
- [ ] T042 [Paso 8] **Verde:**
  - `acceso/`, `busqueda/`, `tablero/` (con la columna "Naturales (no contactables)" y sus claves en es y en, que **viene de 011 (D7)**, T049);
  - `api/cliente.ts`, `compartido/{SelectorIdioma,formato}`;
  - `App.tsx` con el router.

## Fase 10: E2E local (Paso 9) — recortable, segundo en el orden de corte

- [ ] T043 [Paso 9] **Rojo:** `frontend/e2e/busqueda.spec.ts::login_vista_previa_buscar_tablero`, con `backend/tests/stubs/servidor_fuentes.py` vía `CROMA_BASE_URL` y `OVERPASS_URL`. Nunca contra Railway.
- [ ] T044 [Paso 9] **Verde:** el job de CI levanta api, web, Postgres y el stub.

## Fase 11: Cola de revisión (Paso 10) — recortable, primero en el orden de corte

- [ ] T045 [Paso 10] **Rojo (advisor, cumplimiento):** `backend/tests/integration/test_revision_dedup.py`:
  - `::test_fusionar_mueve_lead_fuentes_y_marca_absorbido`. **Mutación:** sin el `DELETE` de los `lead_fuentes` del absorbido.
  - `::test_superviviente_es_el_que_tiene_id_fiscal`. **Mutación:** sobrevive siempre `lead_a`.
  - `::test_fusionar_con_id_fiscal_distinto_da_409`. **Mutación:** sin el veto.
  - `::test_resolver_dos_veces_da_409`. **Mutación:** sin el filtro `estado='pendiente'`.
  - `::test_fusionar_cierra_las_otras_pendientes_del_absorbido[x_mayor|x_menor]`. **Mutación:** insertar `(superviviente, X)` sin `least`/`greatest` → viola el `CHECK` en `x_menor`.
  - `::test_revision_con_lead_ya_fusionado_da_409`. **Mutación:** no chequear `fusionado_en` de los dos leads.
  - `::test_cumplimiento_de_ambos_queda_intacto`. **Mutación:** borrar el `cumplimiento` del absorbido.
  - `::test_separar_no_toca_leads`. **Mutación:** `separar` llama a `aplicar_fusion`.
  - `::test_cola_no_expone_contacto`. **Mutación:** `SELECT leads.*` en el repo.
- [ ] T046 [Paso 10] **Verde:** `resolver_revision.py` y el router `dedup`.
- [ ] T047 [P] [Paso 10] **Rojo:** `frontend/src/dedup/ColaRevision.test.tsx::lista_pares_y_resuelve`. No está en la spec; lo suma el plan, porque la pantalla no puede quedar sin test (principio II). **Mutación:** el botón Fusionar manda `separar`. **Verde:** `dedup/ColaRevision.tsx`.

## Fase 12: Corrida real (Paso 11)

- [ ] T048 [Paso 11] Vista previa + Buscar contra Croma, avisada antes. Se anota el saldo antes y después (esperado: 1 request y 1 crédito), si viene `total` y el tiempo de ejecución (umbral de 30 s).

## Fase 13: Docs (Paso 12)

- [ ] T049 [Paso 12] `docs/arquitectura-backend.md`: vistas, lote = búsqueda, auth y cómo se agrega una columna al tablero.
- [ ] T050 [P] [Paso 12] `docs/arquitectura-frontend.md`: la estructura por feature, la regla de límites y cuándo algo pasa a `compartido/`.
- [ ] T051 [P] [Paso 12] La corrección de `docs/prd.md` §4: `croma_consulta` es de lote, y Overpass registra solo segundos. Además, `spec.md` se alinea con P5 y P8 una vez que el dueño las resuelva.

## Dependencias y paralelismo

- T001 bloquea todo. T004 va antes de cualquier rojo de Python.
- Fase 2 → Fase 3 → Fase 4. La Fase 5 puede correr en paralelo con la Fase 4.
- Las Fases 4 y 5 → Fase 6 → T028.
- La Fase 7 solo necesita la Fase 2. Las Fases 6 y 7 → Fase 8 → Fase 9 → Fase 10.
- La Fase 11 solo necesita la Fase 8.
- Se pueden correr en paralelo T017, T018 y T019; T022 con la Fase 4; T039, T040 y T041.

## Orden de corte (spec:499-506)

1. Fase 11 (cola de revisión).
2. Fase 10 (E2E).
3. T022–T023 (4b, palabras clave): pasan a la 010.
4. `v_costo_por_canal` y `test_costo_por_canal`: pasan a la 007.
5. Cobertura por país y revisiones pendientes en el tablero.

**No se cortan:** los tests de vistas, la RLS de vistas y de `usuarios`, el contrato de `contar` (incluido `[datos_gov_co_rues]`), el tope con sus tres adaptadores, auth, ni los 6 tests de la D7 con su verde.

## Los 6 tests que vienen de 011 (D7)

| ID 011 | Test | ID 005 |
|---|---|---|
| T035 | `test_fuente_descubrimiento.py::test_contar_registra_costo_antes_de_devolver[datos_gov_co_rues]` | T016 |
| T035 | `test_fuente_descubrimiento.py::test_contar_devuelve_entero_no_negativo_o_none[datos_gov_co_rues]` | T016 |
| T035 | `test_fuente_descubrimiento.py::test_contar_rechaza_criterio_no_soportado[datos_gov_co_rues]` | T016 |
| T035 | `test_datos_gov_co.py::test_costo_maximo_llamada` | T019 |
| T047 | `test_api_busquedas.py::test_tablero_trae_naturales_por_fuente` | T031 |
| T048 | `Tablero.test.tsx::muestra_naturales_encontradas_no_contactables` | T041 |
| T049 | el verde del tablero (endpoint, columna e i18n) | T032 y T042 |
