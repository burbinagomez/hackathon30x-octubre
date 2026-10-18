# Tasks: 005 — Libro de costos, CPL por fuente y "Nueva búsqueda"

**Input**: `spec.md` y `plan.md` de esta carpeta.

**Formato**: `- [ ] TNNN [P?] [Paso n] descripción con ruta`.
- **Rojo** = test que falla **por aserción**. Nunca `xfail` plano, `ImportError` ni `AttributeError`: antes de cada rojo va un esqueleto que importa y devuelve un valor equivocado.
- **Mutación** = el cambio de una línea en el código que tiene que poner ese test en rojo. Si un test nace verde, se acepta solo si su mutación lo pone en rojo; la mutación se aplica, se ve el rojo y se revierte.
- **Decimal**: todo monto se asierta con `type(v) is Decimal` y contra `Decimal("…")` construido desde string. Con una mutación float, `2.0 == Decimal(2)` da `True` y no hay rojo; por eso los esperados no son enteros y se chequea el tipo.
- **(advisor)** / **(security)**: el test lo revisa ese agente **antes** de aceptarlo. Cubre costos, fórmulas CPL/CPQL, cumplimiento y RLS.
- **viene de 011 (D7)**: test movido desde la 011, con el mismo nombre (ver Fase 4, Fase 8 y Fase 9).
- **[MIN]** / **[Pulido]**: ver "Estrategia: primero que funcione" al final. Una `[MIN]` marcada como parcial entra al mínimo solo con lo que dice la tabla "Qué entra al [MIN]"; el resto de esa tarea va a Pulido.

## Fase 1: Puerta y setup

- [x] T001 [MIN] [Paso 0] **Puerta.** `git fetch origin`. Confirmar que 002, 003 y 011 están en `main` (la 004 no es requisito: decisión del dueño, plan.md, Preguntas abiertas). Elegir el número de migración: el siguiente libre en `supabase/migrations/` (P5). Se frena en dos casos:
  - P1 (estados, y qué deja la CLI) no tiene respuesta del dueño;
  - el default de P2 no está aprobado.

  El default de P4 frena solo la Fase 4, que es Pulido: el [MIN] arranca sin él.
- [x] T002 [MIN] [P] [Paso 0] `backend/pyproject.toml` suma `PyJWT`. `uv lock`. *(Con Supabase Auth pasa a `pyjwt[crypto]`; el cambio entra en T013.)*
- [ ] T003 [MIN] [P] [Paso 0] `frontend/package.json` suma `react-i18next` e `i18next` como dependencias, y `eslint`, `typescript-eslint`, `eslint-plugin-boundaries`, `eslint-plugin-import`, `eslint-import-resolver-typescript` y `eslint-plugin-i18next` como devDependencies. *Auditoría 2026-10-18: falta `eslint-plugin-boundaries` en devDependencies (se sacó por CVE, PR #37); lo demás está*
- [ ] T004 [MIN] [Paso 0] **Esqueletos de Python.** Las firmas del plan, que devuelven valores equivocados para que los rojos sean por aserción:
  - `contar` → `-1` en Croma y OSM. **`datos_gov_co_rues` queda afuera:** la 011 ya implementa `contar` completo (011 tasks c64c5f8:163-173), y un stub rompería `test_contar_usa_count_con_el_mismo_where` de la 011;
  - `FabricaFuentes` (Protocol en `descubrimiento/dominio/`);
  - `VerificadorToken` (Protocol) y `TokenInvalido` en `acceso/dominio/`; el verificador esqueleto devuelve un `sub` fijo sin validar. *(El `hmac_email` del esqueleto ya hecho se borra en T013.)*
  - `gasto_busqueda` → `Decimal("-1")`;
  - `costo_maximo_llamada = Decimal("0")`;
  - `filtrar_por_palabras` → `[]`;
  - `VistaPrevia` y `EjecutarBusqueda` → resultados vacíos;
  - los routers registrados, que devuelven `501`.

  *Hecho (parte [MIN]), verificado 2026-10-18:* `FabricaFuentes`, `VerificadorToken` y `TokenInvalido` (`acceso/dominio/`), `VistaPrevia` y los routers `busquedas`, `tablero` y `actividades` en 501 (el de `auth` ya no existe: Supabase Auth; `hmac_email` se borró en T013). *Falta:* el esqueleto de `EjecutarBusqueda`, que se diseña en T026 junto con su signature (`ejecutar(busqueda_id)`): hoy la clase es la de la 003, con `ejecutar(criterios)` y tests propios.

## Fase 2: Migración y vistas (Paso 1)

- [x] T005 [MIN] [Paso 1] **Esqueleto de la migración** `supabase/migrations/NNNN_libro_costos_busqueda.sql`: *Auditoría 2026-10-18: falta `leads.fusionado_en` y las 7 vistas de costo (solo existen `v_tablero_fuentes` reducida y `v_atribuciones`); lo de [MIN] está hecho*
  - las columnas e índices de plan §Migración. `leads.fusionado_en` va con FK **simple** `REFERENCES leads(id)`; la compuesta entra en T011, después del rojo;
  - `usuarios` con sus columnas (`auth_user_id uuid PRIMARY KEY`, `tenant_id`, `idioma`, `creado_en`; sin email), **sin** `CHECK` y **sin** RLS;
  - `tenant_de_usuario` (y `fijar_idioma`, Pulido) como stubs `… WHERE false`, **sin** `SECURITY DEFINER` ni `REVOKE`;
  - las 9 vistas con sus columnas finales, `WHERE false` y **sin** `security_invoker`.

  `app/modelos.py` se actualiza a la par.
  *Verificado 2026-10-18 (verificado y cerrado): el esqueleto lo reemplazó la 0006 final (T013) y todo su contenido [MIN] está en la base. Desde vacío (postgres:16, puerto 5434) las 8 migraciones aplican y el re-run no aplica nada; en la base: `busquedas_estado_check` con los 8 estados (P1); `usuarios` con `auth_user_id` PK, FK a `tenants`, `usuarios_idioma_check`, la política `tenant_aislado` idéntica a la de `leads` y `app_rt` sin `SELECT` sobre la tabla; `tenant_de_usuario` `SECURITY DEFINER` con `search_path=public, pg_temp` y ACL solo `postgres`+`app_rt` (ni `PUBLIC` ni `anon`/`authenticated`); `v_tablero_fuentes` y `v_atribuciones` con `security_invoker=true` y `SELECT` a `app_rt`; `modelos.py` a la par (drift verde). **Sabotaje:** quitar `ENABLE ROW LEVEL SECURITY` de `usuarios` en la 0006 y reconstruir la base → rojo en `test_rls.py::test_usuarios_tiene_rls` y en `test_migracion_0006.py` (el archivo == bloque aprobado de `plan.md`); aplicado, visto el rojo y revertido (`git checkout`, árbol limpio, 2 passed). Fase 2: 53 tests verdes; suite completa 1239 passed / 7 xfailed; `lint-imports`, 10 contratos. **No queda nada de T005:** lo que falta es el Pulido de tareas [MIN] posteriores —`leads.fusionado_en` con su FK compuesta (T011), las 6 vistas de costo `v_costos`, `v_costo_evals`, `v_prorrateo`, `v_desperdicio`, `v_costo_por_lead` y `v_costo_por_canal` (T008; `v_leads_icp` ya existe, de la 0008) y `fijar_idioma` (T012/T013)—. Del resto de plan §Migración, sin tarea que lo tome hoy (queda señalado para la cola): las columnas `busquedas.costo_estimado_usd`, `costo_maximo_usd` y `ejecutada_en` (hoy son solo campos de la respuesta de la API), `revision_dedup.motivo` y los índices `costos (tenant_id, lote_id)` y `lead_fuentes (busqueda_id, fuente)` (spec:428-429).*
- [x] T006 [MIN] [Paso 1] `backend/tests/arquitectura/test_migraciones.py::test_migrar_local_desde_vacio_dos_veces_sin_drift` (de la 002) sigue verde con la migración nueva. Se confirma que `compare_metadata` no reporta las vistas. **Mutación:** borrar `fusionado_en` de `modelos.py` → drift.
  *Verificado: verde en la suite; sabotaje `usuarios.auth_user_id` fuera de `modelos.py` -> rojo en `test_migrar_local_desde_vacio_dos_veces_sin_drift` y `test_drift_mira_solo_public...`.*
- [ ] T007 [MIN] [Paso 1] **Rojo (advisor):** `backend/tests/integration/test_vistas_costos.py`, con el fixture de spec:77-112, sembrado con `postgres` y leído como `app_rt`. Cada test, con su mutación: *(parte [MIN] hecha)* *Auditoría 2026-10-18: de los 11 tests solo existen `test_encontrados_y_unicos_por_fuente` y `test_lead_de_dos_fuentes_cuenta_una_vez_en_total`; faltan los de costo, prorrateo, desperdicio, canal y fusionado (el costo por fuente se calcula en `repositorio_tablero.py`, no en vistas)*
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
  *Verificado 2026-10-18 (parte [MIN]): `test_vistas_costos.py:46` (`test_encontrados_y_unicos_por_fuente`) y `:50` (`test_lead_de_dos_fuentes_cuenta_una_vez_en_total`) verdes. Sabotaje `unicos = count(*)` en `v_tablero_fuentes` -> rojo en los dos (`AssertionError` sobre la tabla por fuente y sobre el TOTAL); revertido (base reconstruida, 2 passed).*
- [ ] T008 [MIN] [Paso 1] **Verde:** los cuerpos de las 9 vistas de spec:313-335, el `GRANT SELECT` a `app_rt` y el `CHECK` de `estado` (P1). **Sin `security_invoker`:** esa opción entra solo en T011, para que T009 nazca rojo. *Auditoría 2026-10-18: solo 2 de las 9 vistas existen; faltan las 7 de costo*
- [ ] T009 [MIN] [Paso 1] **Rojo (advisor, RLS):** `backend/tests/integration/test_rls.py`: *Auditoría 2026-10-18: falta `test_tenant_b_no_fusiona_con_lead_de_a` y el `[vista]` de las vistas de costo; la parte [MIN] está hecha*
  - `::test_tenant_b_no_accede_a_datos_de_a[vista]`, sobre cada `v_*`: control positivo de A ≥ 1 fila, B ve 0 filas y 0 filas `TOTAL`. La siembra de A trae una `lead_fuentes` de `osm_overpass`. Rojo hoy: las vistas sin `security_invoker` corren como `postgres`. **Mutación tras el verde:** quitar `security_invoker` de una vista, o quitar `HAVING count(*) > 0` → B ve una fila `TOTAL`.
  - `::test_toda_vista_es_security_invoker`, desde `pg_class`. **Mutación:** una vista sin la opción.
  - `::test_usuarios_tiene_rls`. **Mutación:** sin `ENABLE ROW LEVEL SECURITY`, o sin la política.
  - `::test_tenant_b_no_fusiona_con_lead_de_a`: como `app_rt` con el tenant B, un `UPDATE` de un lead de B con `fusionado_en` = id de un lead de A lanza `ForeignKeyViolation` (sqlstate `23503`). Rojo hoy, porque la FK simple de T005 no pasa por RLS y el `UPDATE` funciona. Control positivo: el mismo `UPDATE` hacia otro lead de B funciona. **Mutación:** FK simple.
  *Verificado (parte [MIN]): `test_usuarios_tiene_rls` existe; sabotaje `DISABLE ROW LEVEL SECURITY` -> rojo; sabotaje `security_invoker=false` en `v_atribuciones` -> rojo en `[v_atribuciones]` y en `test_toda_vista_es_security_invoker`.*
- [x] T010 [MIN] [P] [Paso 1] **Rojo (advisor):** `backend/tests/integration/test_privilegios_supabase.py::test_anon_y_authenticated_sin_privilegios` (de la 002) suma `pg_views`, con el assert previo de que esté `v_tablero_fuentes`. **Mutación:** sacar `pg_views` de la unión (falla el assert previo), o `GRANT SELECT ON v_tablero_fuentes TO anon`.
  - **LOW (security):** `::test_anon_y_authenticated_sin_execute_en_funciones_de_public`: recorre `pg_proc` de `public` y falla si `anon` o `authenticated` pueden ejecutar **cualquier** función (hoy `tenant_de_usuario` y las que vengan). **Mutación:** sacar el `REVOKE` de una función.
- [ ] T011 [MIN] [Paso 1] **Verde:** *Auditoría 2026-10-18: falta la FK compuesta de `fusionado_en`; `security_invoker` y RLS de `usuarios` están hechos*
  - `security_invoker = true` en las 9 vistas;
  - la RLS de `usuarios`;
  - `FOREIGN KEY (tenant_id, fusionado_en) REFERENCES leads (tenant_id, id)`, que se apoya en `leads_tenant_id_id_key` (002 migración:41).
  *Verificado (parte [MIN]): `security_invoker` en las vistas [MIN] y RLS de `usuarios` en la 0006. La FK compuesta de `fusionado_en` es Pulido.*
- [ ] T012 [MIN] [Paso 1] **Rojo (security, RLS):** `backend/tests/integration/test_usuarios_repo.py`: *Auditoría 2026-10-18: falta `fijar_idioma` y su test (`test_fijar_idioma_no_cruza_tenants`); el resto está hecho*
  - `::test_app_rt_no_lee_usuarios_directo`. **Nace verde:** `app_rt` nunca tuvo `SELECT` sobre `usuarios`. Es una guarda. **Sabotaje:** `GRANT SELECT ON usuarios TO app_rt` → rojo, y se revierte. **LOW (security):** el test fija `app.tenant_id` del tenant dueño de la fila y exige sqlstate `42501` (privilegio insuficiente), para que no pase por un error de `current_setting`.
  - `::test_tenant_de_usuario_devuelve_solo_ese_usuario`. Con usuarios de 2 tenants, `tenant_de_usuario(<auth_user_id de A>)` devuelve 1 fila (tenant de A, `idioma_usuario`, `idioma_tenant`) y un uuid inexistente devuelve 0. Rojo hoy: el stub `WHERE false` devuelve 0 filas. **Mutación:** sin el `WHERE u.auth_user_id = p_auth_user_id` → 2 filas.
  - `::test_fijar_idioma_no_cruza_tenants` **(Pulido)**. Control positivo con el tenant de A: `fijar_idioma(<uid de A>, 'en')` modifica 1 fila. Rojo hoy: el stub modifica 0. Después, con el tenant de B sobre el usuario de A, modifica 0. **Mutación:** sin `AND tenant_id = current_setting(...)` → B modifica 1 fila.
  - `::test_tenant_de_usuario_es_security_definer_con_search_path` (y la de `fijar_idioma`, Pulido), con el `ALTER DEFAULT PRIVILEGES` en `supabase_simulado.sql` (ya está). **Mutación:** sin el `REVOKE` → `anon` tiene `EXECUTE`.
  *Verificado (parte [MIN]): sabotaje `GRANT SELECT ON usuarios TO app_rt` -> rojo; `tenant_de_usuario` sin `WHERE` -> rojo en `test_tenant_de_usuario_devuelve_solo_ese_usuario`. `fijar_idioma` es Pulido.*
- [x] T012b [MIN] [P] [Paso 1] **Rojo (security):** `backend/tests/unit/acceso/test_verificar_token.py`, sin red: el test genera un par EC P-256 y le pasa al verificador un JWKS local.
  - `::test_token_valido_devuelve_sub`: devuelve el `sub` (uuid). Rojo hoy: el esqueleto devuelve un `sub` fijo distinto.
  - `::test_token_invalido_lanza[caso]` → `TokenInvalido`: vencido, sin `exp`, sin `sub`, `aud` distinto, `iss` distinto, firmado con otra clave, `alg=none`, HS256 firmado con la clave pública como secreto (confusión de algoritmo) y `kid` ausente del JWKS y `alg=RS256` con el `kid` de la clave EC. Rojo hoy: el esqueleto no lanza (falla el `pytest.raises`). **Mutaciones:** sin `audience`; sin `issuer`; sin `require`; `clave.key` en vez del `PyJWK` entero (muere `alg_rs256_con_kid_ec`); sin el `except` de `PyJWKClientConnectionError` (muere `test_jwks_inaccesible_no_es_token_invalido`); `timeout` distinto de 5. `algorithms` con `HS256`, `algorithms` tomado del header o sin `algorithms` (las mata `::test_clave_simetrica_en_el_jwks_no_valida_tokens_hs256`: JWKS envenenado con una clave `oct`/HS256 y un token HS256 firmado con ella; con el `PyJWK` entero el `alg` del token coincide con el de la clave, así que solo la lista `algorithms` lo rechaza). Caso `nbf_futuro` (muere sin `verify_nbf`).
  - **LOW (security):** `::test_sub_que_no_es_uuid_lanza[caso]` (`sub` ausente de forma de uuid, vacío, numérico): `TokenInvalido`, nunca un `ValueError` sin capturar. **Mutación:** `UUID(sub)` fuera del `try`.
  *Verificado: `test_verificar_token.py` verde con los casos de la tarea (incluye JWKS inaccesible, timeout 5 s y clave simétrica).*
- [ ] T013 [MIN] [Paso 1] **Verde:** *Auditoría 2026-10-18: falta `fijar_idioma` y el procedimiento de baja en `docs/arquitectura-backend.md` (no existe en main)*
  - `tenant_de_usuario` real (`SECURITY DEFINER` con `search_path`), el `REVOKE`/`GRANT` y el `DO` con el guard de `pg_roles`;
  - `acceso/infraestructura/verificador_jwks.py` (`PyJWKClient`, el `PyJWK` entero a `jwt.decode`, `algorithms=["ES256","RS256"]`, `audience`, `issuer`, `require`; `PyJWKClientConnectionError` → `JwksInaccesible`); `pyjwt[crypto]` en `pyproject.toml`; **LOW:** `PyJWKClient(..., timeout=5)` (~5 s): un JWKS colgado no deja colgada la API.
  - `AUTH_JWKS_URL` y `AUTH_ISSUER` en `Settings`, `.env.example` y `docs/referencia-configuracion.md` si existe;
  - `backend/scripts/crear_usuario.py` con `getpass`: inserta la fila de `usuarios` (`--auth-user-id`, `--tenant`);
  - se borran `acceso/dominio/email.py` y `hmac_email`.
  - **El `.sql` final de la 0004 es el bloque aprobado de plan.md**, con `backend/tests/arquitectura/test_migracion_0006.py` que lo compara (rojo antes: el archivo es el esqueleto).
  - **Procedimiento de baja** (LOW): se borra la fila de `usuarios` (la cuenta de Supabase se deshabilita aparte, paso humano); queda escrito en `docs/arquitectura-backend.md` (T049) y en el docstring de `crear_usuario.py`.

**Checkpoint**: vistas, RLS, privilegios y usuarios verdes.
  *Verificado (parte [MIN]): `tenant_de_usuario`, verificador JWKS, `AUTH_*` en `SettingsApi` y `.env.example`, `crear_usuario.py` con `getpass` y procedimiento de baja en el docstring, `hmac_email` borrado (guarda `test_sin_login_propio.py`), `test_migracion_0006.py`. La baja en `docs/arquitectura-backend.md` queda en T049.*
## Fase 3: `gasto_busqueda` y lote (Paso 2)

- [X] T014 [Pulido] [Paso 2] **Rojo (advisor, costos):** `backend/tests/integration/test_costos_repo.py::test_gasto_busqueda_suma_lista_del_lote`, con montos no enteros (`0.40` gratis y `0.07`) y filas de otro lote; espera `Decimal("0.47")`. **Mutación:** sumar `monto_real` → 0.07, o sin el filtro de `lote_id` → incluye el otro lote.
  - `::test_gasto_busqueda_sin_filas_es_cero`: un lote sin filas da `Decimal("0")`, con `type is Decimal`. Rojo hoy: el esqueleto devuelve `Decimal("-1")`. **Mutación:** sin `COALESCE` → `None`, y el tope revienta con `None + Decimal`.
- [X] T015 [Pulido] [Paso 2] **Verde:** `postgres_costos.gasto_busqueda` y el método en el Protocol (P3), más el registro falso compartido de `tests/`.

## Fase 4: `contar()` y `costo_maximo_llamada` (Paso 3)

- [ ] T016 [Pulido] [Paso 3] **Rojo (advisor, costos):** `backend/tests/contratos/test_fuente_descubrimiento.py`, parametrizado sobre el catálogo (`croma_supersociedades_co`, `osm_overpass`, `datos_gov_co_rues`). Los cuatro tests:
  - `::test_contar_registra_costo_antes_de_devolver[…]`. Un caso con éxito y otro con transporte que siempre falla (sale `FuenteNoDisponible`): en los dos hay ≥ 1 fila en el registro falso. **Mutación:** `registrar` solo en el camino feliz.
  - `::test_contar_devuelve_entero_no_negativo_o_none[…]`: `type(r) is int and r >= 0` o `r is None`. **Mutación:** devolver el `total` crudo del JSON (`"2015"`, un str) → rojo por el tipo.
  - `::test_contar_rechaza_criterio_no_soportado[…]`: `CriterioNoSoportado` y 0 requests en el transporte. **Mutación:** validar después del request → 1 request.

  - `::test_costo_maximo_llamada_positivo[…]`: `type(meta.costo_maximo_llamada) is Decimal and > 0`. Sin esta guarda, un adaptador nuevo (por ejemplo `croma_dian_trade_co`, spec:27) entraría al tope como gratis por el default `Decimal("0")`. Rojo hoy en los tres: el esqueleto deja `0`, y la 011 no lo fija. **Mutación:** una fábrica sin `dataclasses.replace`.

  **viene de 011 (D7):** las tres parametrizaciones `[datos_gov_co_rues]` de los tests de `contar` (T035 de la 011). **Nacen verdes,** porque la 011 ya implementa `contar` completo. Cada una se acepta por un sabotaje en `datos_gov_co_rues.py`, que se aplica, se ve rojo y se revierte:
  - `registrar_costo_antes_de_devolver`: `registrar` solo en el camino feliz;
  - `entero_no_negativo_o_none`: devolver `"2015"` como str;
  - `rechaza_criterio_no_soportado`: validar después del request.
- [ ] T017 [Pulido] [P] [Paso 3] **Rojo:** `backend/tests/unit/descubrimiento/test_croma_supersociedades.py`:
  - `::test_contar_lee_total_de_la_pagina_1`, con la fixture sintética con `total=2015` y 100 ítems. **Mutación:** `len(empresas)` → 100.
  - `::test_contar_y_buscar_hacen_una_sola_request`: 1 request y 1 fila. **Mutación:** `contar` con `per_page=1` → otra clave de caché → 2 requests.
  - `::test_ingresos_min_se_envia_como_filtro`. **Mutación:** sacar `ingresos_min` del mapeo de parámetros.
  - `::test_costo_maximo_llamada`: `== Decimal("0.00099")` (1 × `usd_por_credito`). No está en la spec; lo suma el plan para que cs no quede sin test. **Mutación:** usar `creditos_live` (10) → 0.0099.
- [ ] T018 [Pulido] [P] [Paso 3] **Rojo:** `backend/tests/unit/descubrimiento/test_osm_overpass.py`:
  - `::test_contar_usa_out_count`: el body trae `out count;` y no `out center tags`, y lee `int(elements[0].tags.total)`. **Mutación:** reusar la query de `buscar`.
  - `::test_contar_registra_segundos`, con reloj falso y una espera de `Retry-After` de por medio: unidades = segundos del request. **Mutación:** medir desde antes de la espera → incluye los segundos de `sleep`.
  - `::test_costo_maximo_llamada`: `== Decimal("0.00042")` (2 × 30 × 0.0000070). No está en la spec; lo suma el plan. **Mutación:** 1 intento → 0.00021.
- [ ] T019 [Pulido] [P] [Paso 3] **Rojo (advisor, costos):** `backend/tests/unit/descubrimiento/test_datos_gov_co.py`:
  - `::test_costo_maximo_llamada`: `meta.costo_maximo_llamada == Decimal("0.00084")`, que es 2 requests × 2 intentos × 30 s × `computo_seg_usd`, con `type is Decimal`. La fórmula está en la 011 spec (c64c5f8):230. **viene de 011 (D7)** (T035 de la 011). **Mutación:** 2 × 30 (sin las 2 requests) → 0.00042; o calcular con `float` → `0.0008399999…`, rojo por valor y por tipo.
  - `::test_contar_segunda_llamada_sale_del_cache`: dos `contar` con los mismos criterios dan 1 request y 1 fila de costo. Es nuevo en la 005 por el advisor de la 011: la 011 deja el discriminador en `tipo: filas|naturales`. **Rojo natural:** sin `tipo: contar`, `contar` no cachea → 2 requests. **Mutación tras el verde:** `contar` con el discriminador `filas` → choca con la clave de filas, y el test agrega un `buscar` previo con los mismos criterios para que la mutación dé rojo.
  - Los tests que quedan en la 011 (`test_contar_usa_count_con_el_mismo_where` y `test_contar_registra_socrata_descarga`) **no se duplican**.
- [ ] T020 [Pulido] [Paso 3] **Verde:**
  - `contar` en el Protocol y en Croma y OSM. En `datos_gov_co_rues` ya está, por la 011;
  - `costo_maximo_llamada` calculado en cada fábrica (P4);
  - `tipo: contar` en el discriminador de caché de `datos_gov_co_rues`;
  - `CROMA_BASE_URL` en `Settings`.

**Checkpoint**: la suite de contrato, verde con los tres adaptadores.

## Fase 5: Selección y post-filtro (Paso 4)

- [ ] T021 [Pulido] [Paso 4a] **Caracterización:** `backend/tests/unit/descubrimiento/test_seleccion_fuentes.py::test_tamano_es_refinamiento_no_requisito` (archivo de la 003, ver P8). Puede nacer verde (P9). **Mutación:** en `seleccionar_fuentes`, descartar la fuente que no declara `ingresos_min` → OSM queda descartada. El advisor confirma.
- [ ] T022 [Pulido] [P] [Paso 4b] **Rojo:** `backend/tests/unit/descubrimiento/test_palabras_clave.py`:
  - `::test_coincide_por_token_normalizado`. **Mutación:** comparar sin `normalizar_nombre` → la tilde no matchea; o usar substring (`in`) → `"pan"` matchea `"panaderia"`.
  - `::test_exclusion_gana_sobre_palabra_clave`. **Mutación:** devolver `True` en cuanto matchea la palabra clave, antes de mirar las exclusiones.
  - `::test_palabra_clave_de_varios_tokens_exige_todos`. **Mutación:** `any` en lugar de `all`.
  - `::test_sin_palabras_ni_exclusiones_pasa_todo`. **Mutación:** `any([])` como condición → no pasa nada.
- [ ] T023 [Pulido] [Paso 4b] **Verde:** `descubrimiento/dominio/palabras_clave.py`, puro, con el normalizador de la 003.

## Fase 6: `VistaPrevia` y `EjecutarBusqueda` con tope (Paso 5) — advisor

- [ ] T024 [MIN] [Paso 5] **Rojo (advisor, costos):** `backend/tests/unit/descubrimiento/test_vista_previa.py`, con una `FabricaFuentes` falsa (que devuelve fuentes falsas y registra el `lote_id` con el que se la llamó), un repo falso y un libro falso: *Auditoría 2026-10-18: faltan los tests de costo estimado, costo máximo, tope y créditos restantes (`contar`/`costo_maximo_llamada` no existen)*
  - `::test_conteo_por_fuente_y_motivo_de_las_descartadas` (`pais=PE`). **Mutación:** no copiar `ignoradas` a la respuesta.
  - `::test_crea_busqueda_en_borrador_con_criterios`: queda en estado `borrador`, y la fábrica se llamó una vez con `lote_id == borrador.id`. **Mutación:** usar `crear_busqueda` del 002 → estado `creada`; o pedir las fuentes antes de crear el borrador → `lote_id=None`.
  - `::test_ignorados_son_los_criterios_que_la_fuente_no_aplica_y_el_ciiu_traducido_no_cuenta` **(P7, advisor T024)**: `ignorados` por fuente, ordenado; el `ciiu` que se aplica traducido a `tipo_negocio` no es ignorado. **Mutación:** derivar `set(criterios.filtros) - set(sel[k].filtros)` sin sacar el `ciiu` → OSM trae `ciiu`; o sin `sorted`.
  - `::test_fuente_no_disponible_da_conteo_null_y_sigue`. **Mutación:** dejar que la excepción se propague → cs no tiene conteo.
  - `::test_limite_agotado_da_conteo_null`. **Mutación:** mapear todo error a `no_disponible`.
  - `::test_costo_estimado_suma_lo_gastado_y_lo_que_falta`: el gastado sale del libro falso (`Decimal("0.00113")`) + 0 de cs + segundos de OSM × 0.0000070. **Mutación:** sumar 1 crédito de cs aunque haya caché.
  - `::test_costo_maximo_suma_costo_maximo_llamada_de_cada_fuente`. Tres casos:
    - cs + OSM: gastado + 0.00099 + 0.00042;
    - cs + OSM + `datos_gov_co_rues`: + 0.00084 (el agregado del advisor de la 011);
    - borde: `dentro_del_tope` es `False` con un tope de un centavo menos y `True` con un tope igual al máximo.

    **Mutación:** iterar sobre un subconjunto fijo de claves (sin `datos_gov_co_rues`) → falla el segundo caso; o `<` en lugar de `≤` → falla el borde.
  - `::test_reporta_creditos_y_requests_restantes`: 63 y 288. **Mutación:** devolver lo usado en lugar de lo restante.
- [x] T025 [MIN] [Paso 5] **Verde:**
  - `descubrimiento/aplicacion/vista_previa.py`, que recibe `FabricaFuentes`;
  - los métodos de borrador de `RepositorioLeads` (P2);
  - `ignorados` derivado (P7, corregido): `sorted(…)` como en plan.md P7.

  La implementación real de `FabricaFuentes` va en `app/api` (raíz de composición). `aplicacion/` no importa el catálogo concreto, y lo vigila import-linter.
  *Hecho 2026-10-18 (parte [MIN]): `crear_borrador`, `obtener_borrador` y `pasar_a_ejecutando` en el Protocol y en `RepositorioLeadsPostgres` (4 tests en `test_leads_repo.py`), `Borrador` en el dominio, `VistaPrevia` con `ignorados` ordenado (P7 corregido). Sabotajes vistos en rojo: copiar `ignoradas`, `crear_busqueda` del 002, fuentes antes del borrador, ciiu traducido como ignorado, `ignorados` sin ordenar, `obtener_borrador` sin filtro de estado, `pasar_a_ejecutando` sin `AND estado='borrador'`.*

- [ ] T026 [MIN] [Paso 5] **Rojo (advisor, costos y cumplimiento):** `backend/tests/unit/descubrimiento/test_ejecutar_con_tope.py`, con la misma `FabricaFuentes` falsa de T024: *Auditoría 2026-10-18: faltan los tests de tope (`test_no_ejecuta_si_costo_maximo_supera_tope`, `test_corta_antes…`) y de palabras clave*
  - `::test_no_ejecuta_si_costo_maximo_supera_tope`: `TopeExcedido`, 0 requests, estado `borrador`. **Mutación:** chequear el tope después de `pasar_a_ejecutando`.
  - `::test_corta_antes_de_la_llamada_que_pasaria_el_tope`. **Mutación:** chequear después de llamar → OSM se llama.
  - `::test_solo_ejecuta_borrador`: `BusquedaYaEjecutada`. **Mutación:** ignorar el `bool` de `pasar_a_ejecutando`.
  - `::test_usa_los_criterios_guardados`, con un `assert` sobre `inspect.signature(ejecutar)`. **Mutación:** aceptar `criterios=None` y usarlo si viene.
  - `::test_filtradas_por_palabras_no_generan_lead_ni_cumplimiento`: el repo falso no recibe `obtener_o_crear_lead` para la filtrada, y el costo de la llamada sigue en el lote. **Mutación:** filtrar después de persistir.
  *Rojo escrito 2026-10-18, pendiente de advisor (parte [MIN]): `test_ejecutar_con_tope.py` con `test_usa_los_criterios_guardados`, `test_solo_ejecuta_borrador`, más tres que el [MIN] necesita y la tabla no listaba: `test_lote_es_la_busqueda_y_cada_llamada_deja_su_costo_y_cada_lead_su_cumplimiento`, `test_pierde_la_carrera_por_el_borrador_no_llama_a_ninguna_fuente` (mata "ignorar el bool de `pasar_a_ejecutando`", que el secuencial no distingue) y `test_estado_final_completada_si_una_fuente_respondio_y_error_si_fallaron_todas` (P1). Los de tope y palabras clave siguen en Pulido. Esqueleto: clase `EjecutarBorrador` (decisión abierta con el advisor: clase aparte para no romper la CLI y los tests de la 003).*
  *Decisiones del advisor (APROBADO CON CAMBIOS, 2026-10-18):* `EjecutarBorrador` aceptado (nombre y clase aparte), pero el bucle de fuentes, `normalizar_nit`, el dedup, `agregar_lead_fuente` y el armado de errores viven en **una** función privada compartida con `EjecutarBusqueda`, sin copiarlos. `RepositorioLeads.estado(busqueda_id) -> str | None` por RLS (otro tenant -> `None`); el caso de uso levanta `BusquedaNoEncontrada` (404) o `BusquedaYaEjecutada` (409) y el router solo traduce. Sin fuente que cubra el ICP: `completada` con `sin_fuente_para`, sin llamar a ninguna. Tope de gasto: Pulido (ver "Qué se deja afuera"). Rojos endurecidos: `criterios_por_fuente` (dict por clave), cumplimiento exacto por lead, mismo NIT en dos fuentes, estado de la búsqueda tras la carrera y tras el 409, búsqueda inexistente o ajena, sin fuente que cubra.*

- [ ] T027 [MIN] [Paso 5] **Verde:** `EjecutarBusqueda` con tope, `lote_id = busqueda.id`, estado final (P1) y `naturales_por_fuente` (011). *Auditoría 2026-10-18: falta el tope de gasto y `naturales_por_fuente`; `EjecutarBorrador` con lote y estado final está hecho*
  *Hecho 2026-10-18 (parte [MIN]): `_correr_fuentes` compartida por `EjecutarBusqueda` (CLI, sin cambios de comportamiento) y `EjecutarBorrador` (API); `RepositorioLeads.estado`; `BusquedaNoEncontrada`/`BusquedaYaEjecutada`; cierre en `error` ante una excepción inesperada. Sabotajes vistos en rojo y revertidos: ignorar el bool de `pasar_a_ejecutando`, sin `BusquedaNoEncontrada`, sin cierre en `error`, cualquier fuente caída es `error`, fuentes intercambiadas, sin fuente deja `terminada`, sin `normalizar_nit`, licencia de otra fuente en `lead_fuentes`.*

- [ ] T028 [Pulido] [Paso 5] **Rojo (advisor, costos):** `backend/tests/integration/test_costos_repo.py::test_costos_de_descubrimiento_llevan_lote_de_la_busqueda` (spec:141), con transportes falsos y `postgres_costos` real. **Mutación:** construir los adaptadores de la vista previa con `lote_id=None`. Va acá y no en la Fase 3 porque necesita los dos casos de uso.

## Fase 7: Auth (Paso 6) — security

- [ ] T029 [MIN] [Paso 6] **Rojo (security):** `backend/tests/integration/test_auth.py`: *Auditoría 2026-10-18: faltan `test_fijar_idioma_persiste` y `test_fijar_idioma_invalido_da_422` (no existe `PATCH /usuarios/me`)*
  - `::test_token_valido_resuelve_el_tenant_desde_usuarios`: un token con `tenant_id` (o `user_metadata.tenant_id`) de B y el `sub` de un usuario de A actúa como A. **Mutación:** leer el tenant del claim.
  - `::test_token_valido_sin_fila_en_usuarios_da_403`: cuerpo `sin_acceso`; y borrar la fila corta el acceso con el mismo token. **Mutación:** `tenant_actual` cae a un tenant por defecto.
  - `::test_sin_token_da_401[ruta]`, sobre `app.routes` menos `/health`. **Mutación:** una ruta sin la dependencia `tenant_actual`.
  - `::test_token_invalido_da_401[caso]`: los de T012b, por la API. **Mutación:** `except Exception: pass` en el verificador.
  - `::test_app_no_arranca_sin_auth_jwks_url_ni_issuer`, y `::test_jwks_inaccesible_da_503` (nunca 200). **Mutación:** devolver el `sub` sin verificar si el JWKS falla.
  - `::test_docs_desactivadas`. **Mutación:** `docs_url` por defecto.
  - `::test_cors_solo_permite_web_origin`. **Mutación:** `allow_origins=["*"]`.
  - `::test_token_no_aparece_en_logs`. **Mutación:** `logger.info(authorization)`.
  - `::test_usuarios_me_devuelve_idioma[caso]`. **Mutación:** `COALESCE(usuarios.idioma, tenants.idioma)` → `idioma_usuario` nunca es `null`.
  - `::test_fijar_idioma_persiste` **(Pulido)**. **Mutación:** devolver 204 sin llamar a `fijar_idioma`.
  - `::test_fijar_idioma_invalido_da_422[caso]` **(Pulido)**. **Mutación:** modelo sin `extra='forbid'`.
- [ ] T030 [MIN] [Paso 6] **Verde:** *Auditoría 2026-10-18: falta `PATCH /usuarios/me`*
  - `repositorio_usuarios.py` (llama a `tenant_de_usuario`);
  - `app/api/sesion.py` (Bearer → `VerificadorToken` → `tenant_de_usuario(sub)` → `tenant_actual`);
  - `GET /usuarios/me` y `PATCH /usuarios/me` → Pulido;
  - `web_origin` en `Settings` → reemplazado por `CORS_ORIGINS` (plan.md:359);
  - docs off y CORS.

## Fase 8: Endpoints (Paso 7)

- [ ] T031 [MIN] [Paso 7] **Rojo:** `backend/tests/integration/test_api_busquedas.py`: *Auditoría 2026-10-18: falta `test_ejecutar_con_costo_maximo_sobre_tope_da_409` y `test_tablero_trae_naturales_por_fuente`*
  - `::test_tenant_sale_del_token_no_del_body` (advisor, RLS). **Mutación:** modelo sin `extra='forbid'` → 201 en lugar de 422.
  - `::test_tenant_b_no_ejecuta_busqueda_de_a` (advisor, RLS). **Mutación:** abrir la unidad de trabajo con el tenant de la búsqueda en lugar del del token.
  - `::test_ejecutar_dos_veces_da_409`. **Mutación:** mapear `BusquedaYaEjecutada` a 500.
  - `::test_ejecutar_con_costo_maximo_sobre_tope_da_409` (advisor, costos): 0 filas nuevas en `costos`. **Mutación:** llamar `contar` de nuevo antes de chequear.
  - `::test_validacion[caso]`. **Mutación:** sin `le=TOPE_MAXIMO_USD`, o sin validar `canal_preferido` contra el YAML.
  - `::test_tablero_devuelve_null_para_cpl_sin_divisor`. **Mutación:** serializar `None` como `"0"`.
  - `::test_vista_previa_devuelve_motivos_como_codigo`. **Mutación:** devolver `msg` de pydantic.
  - `::test_actividades_trae_ambos_nombres`. **Mutación:** omitir la clave `nombre_en` cuando es `null`.
  - `::test_tablero_atribucion_solo_de_fuentes_presentes[caso]` (advisor, cumplimiento). **Mutación:** sin el `EXISTS` → `solo_croma` trae dos.
  - `::test_tablero_trae_naturales_por_fuente`. **viene de 011 (D7)** (T047 de la 011). Definición en la 011 spec (c64c5f8):135. Las dos búsquedas se siembran con `creado_en` **explícito y distinto**. Con `DEFAULT now()`, dentro de una misma transacción empatan: `DISTINCT ON` elegiría al azar, y la mutación ASC no daría rojo. **Mutación:** `COALESCE(naturales, 0)` → OSM trae `0` en lugar de `null`; o `ORDER BY fuente, creado_en ASC` → toma el conteo viejo.
  *Van a Pulido (el [MIN] no los pide): `::test_ejecutar_con_costo_maximo_sobre_tope_da_409`, `::test_tablero_devuelve_null_para_cpl_sin_divisor` y `::test_tablero_trae_naturales_por_fuente` (D7). El [MIN] sí fija que el tablero completa con `null` lo que no calcula (`test_tablero_completa_con_null_lo_que_el_minimo_no_calcula`).*
  *Rojo escrito 2026-10-18, pendiente de advisor (RLS y cumplimiento) (parte [MIN]): `test_api_busquedas.py`, 21 casos en rojo por assert (`501 == 201/200/422`; `['4711', '5611', '4752'] == []` para el YAML de actividades). Más lo que el [MIN] necesita y la tabla no listaba: 404 frente a 409 entre tenants (ajena indistinguible de inexistente, sin requests ni costos), `test_validacion_ciiu_devuelve_el_nombre_de_la_regla`, `test_actividades_yaml_real_tiene_nombre_es_en_todas_las_entradas`, y `test_flujo_completo_deja_leads_costos_y_cumplimiento_del_tenant` (vista previa -> ejecutar -> tablero con fuentes reales y transporte falso: costos con `lote_id` = búsqueda y `lead_id` null, un `cumplimiento` por lead, nada en B). Contrato del verde: `app.state.transporte_http` y `app.state.actividades_yaml`; vista previa 201, ejecutar 200; errores 422 como `{errores: [{campo, codigo}]}`.*
  *Verde 2026-10-18 con T032 (parte [MIN]); 27 casos en `test_api_busquedas.py` + `tests/unit/api/`. Ajuste a lo pedido: `base_legal` NO se exige no nula en `cumplimiento` (la setea AprobarMensaje en el 007: 0002 migración:68, 003 spec:344); el test exige que sea NULL en todos, para que nadie la rellene con `persona_juridica_canal_publicado` a un lead de OSM (`desconocido` = natural).*
- [ ] T032 [MIN] [Paso 7] **Verde:** *Auditoría 2026-10-18: faltan `limites_app` en `tarifas.yaml` y el tablero de naturales (`tablero.py` devuelve `cuenta_naturales: False` y `null`)*
  - routers `busquedas`, `tablero`, `actividades`;
  - `repositorio_tablero.py`;
  - `limites_app` en `tarifas.yaml` (P11);
  - `nombre_es`/`nombre_en` en `actividades.yaml`;
  - el verde del tablero de naturales: `DISTINCT ON (fuente) … ORDER BY fuente, creado_en DESC` (la columna ya existe en la 002) sobre las búsquedas `completada`, o `IN ('completada','terminada')` según lo que decida el dueño en P1; **viene de 011 (D7)** (T049 de la 011).
  *Hecho 2026-10-18 (parte [MIN]): `app/composicion.py` (CLI y API comparten `armador_de_fuente`; `registro_api` sin Croma), routers `busquedas`, `tablero` (con `null` en lo no calculado) y `actividades`, `repositorio_tablero.py`, `nombre_es`/`nombre_en` en `actividades.yaml`, `canal:` en `canales_contacto`, 422 como `{errores: [{campo, codigo}]}`. Front en el mismo PR: tipos `| null`, `puedeBuscar` con `!== false`, líneas de costo/tope y columnas de costo ocultas si vienen `null`, `motivos.sin_conteo` y `criterios.{ciudad,palabras_clave,exclusiones}` en es/en. Sabotajes vistos en rojo: sin `extra=forbid`, 409 sin mapear, ajena responde 409, sin validar canal, palabras clave descartadas, error de fuente como frase, `unicos` desde `encontrados`, sin `nombre_en` cuando es null, 422 con `msg`, lifespan que hereda estado, `registro_api` sin filtro de Croma, datos.gov.co sin el transporte inyectado; front: `puedeBuscar` exige true, tope con costo máximo null, columnas de costo siempre, cobertura null sin guarda.*
  *Geografía (aprobada por Daniel, 2026-10-18): cascada país -> división -> ciudad, un archivo por país en `backend/config/geografia/` (hoy `co.yaml`, generado por `backend/scripts/geografia_co.py`, que no corre en runtime ni en CI). Cada división lleva `iso_3166_2` (común), `codigo_nativo` (DIVIPOLA, lo que usan los adaptadores), `nombre_es`/`nombre_en` y `municipios`. `GET /geografia` lista los países con archivo; `?pais=CO` sus divisiones; `filtros.departamento` = código nativo y `filtros.ciudad` = nombre del municipio; 422 `desconocido`/`requerido` por campo. La etiqueta de la división sale de i18n por país (`geografia.division.*`). **Pendiente con red:** `co.yaml` tiene los 33 departamentos y 0 municipios (datos.gov.co da 403 desde este entorno); correr `python scripts/geografia_co.py` con red y verificar el id del dataset (`gdxc-w37w`, no verificado) y que los nombres en título coincidan con los de OSM. **`camaras_co.yaml` no cubre `73` (Tolima) ni la mayoría de los departamentos** (solo 04, 14, 47 y 58, de Bogotá y Cundinamarca): con Tolima, datos.gov.co responde `criterio_no_soportado` y la búsqueda sigue con OSM.*
- [x] T033 [MIN] [Paso 7] `EXCLUIDOS` de los tests de arquitectura de la 002 suma `repositorio_tablero.py` y `repositorio_usuarios.py` (P10). `uv run lint-imports` verde. **LOW (security):** `usuarios` entra a `EXCLUIDAS` de `test_rls.py` con el motivo "`app_rt` no tiene privilegios; entra solo por `tenant_de_usuario`; su RLS la prueba `test_usuarios_tiene_rls`".

## Fase 9: Front (Paso 8)
  *Hecho 2026-10-18: en esta rama no existe el `EXCLUIDOS` de arquitectura de la 002 (solo el de `test_required_checks.py`, que es de CI); `repositorio_tablero.py` y `repositorio_usuarios.py` no escriben ni llaman a fuentes, así que no hay nada que excluir. `usuarios` ya está en `EXCLUIDAS` de `test_rls.py` con su motivo. `lint-imports` verde (5 contratos).*
- [x] T034 [MIN] [Paso 8] Mover `src/setupTests.ts` a `src/test/setup.ts` y sumar `src/test/servidor.ts` (MSW sin handlers). `vitest.config.ts` incluye `src/**` y `tests/**` y excluye `e2e/`.

  **Esqueletos del front,** para que los rojos de T035–T041 y T047 fallen por aserción y no por "module not found" ni ENOENT:
  - `Login`, `NuevaBusqueda`, `Tablero` y `ColaRevision` devuelven `null`;
  - `api/cliente.ts` exporta sus funciones sin tocar el token;
  - `elegirIdioma` devuelve `'xx'`;
  - `src/i18n/es.json` y `en.json` son `{}`;
  - `frontend/eslint.config.js` es `export default []`, para que `overrideConfigFile` de `limites.test.ts` encuentre el archivo.

  Un test que nazca verde contra estos esqueletos (por ejemplo, un positivo de `limites.test.ts` con la config vacía) se acepta solo si su mutación lo pone en rojo.
- [ ] T035 [MIN] [Paso 8] **Rojo:** `frontend/tests/arquitectura/limites.test.ts`, los 6 tests de spec:221-235. **Mutación:** cada negativo, con su dirección en `allow`; para `import_sin_resolver_es_error`, `import/no-unresolved` en `off`. *Auditoría 2026-10-18: existe `el_repo_no_tiene_violaciones` pero no los 6 tests de límites ni `boundaries` (T036 sigue sin hacerse)*
- [ ] T036 [Pulido] [Paso 8] **Verde:** `frontend/eslint.config.js` (boundaries, en el orden de tipos de spec:445-452, más el resolver de TS). *Auditoría 2026-10-18: `eslint.config.js` solo tiene la regla i18next; no hay reglas de límites*
  - Nota: `eslint-plugin-boundaries` se sacó de devDependencies (PR #37) porque arrastra handlebars 4.7.9 (3 CVE críticos) y braces 3.0.3 (CVE alto, sin versión arreglada) y rompía `npm audit`. Al retomar la T036, elegí un plugin sin braces vulnerable: `eslint-plugin-import`, ya instalado, trae `import/no-restricted-paths`.
- [x] T037 [MIN] [Paso 8] **Rojo:**
  - `frontend/tests/arquitectura/i18n.test.ts`, los 4 tests. **Mutación:** borrar una clave de `en.json`; `mode` que no atrapa atributos.
  - `frontend/src/i18n/elegirIdioma.test.ts::precedencia[caso]`. **Mutación:** el tenant antes que el navegador.
- [x] T038 [MIN] [Paso 8] **Verde:** `src/i18n/` y la regla `i18next/no-literal-string`.
- [x] T039 [MIN] [P] [Paso 8] **Rojo:** *(variables del servicio web en Railway, build args: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`; ver README y `frontend/Dockerfile`. En el build, `sin_secretos` busca `sb_secret_` + cuerpo de key y no el prefijo suelto, porque `supabase-js` lo trae para rechazar esas keys.)*
  - `frontend/src/acceso/Login.test.tsx::login_con_supabase_pide_usuarios_me`: inicia sesión con `supabase-js` (mockeado) y llama a `GET /usuarios/me` con el access token. **Mutación:** llamar a la API sin el `Bearer`.
  - `frontend/src/acceso/Login.test.tsx::selector_sin_sesion_no_guarda`. **Mutación:** `PATCH` sin mirar la sesión.
  - `frontend/src/api/cliente.test.ts::un_401_lleva_al_login_y_borra_el_token`. **Mutación:** no borrar el token.
  - **LOW (security):** `frontend/tests/arquitectura/sin_secretos.test.ts`: ningún archivo de `src/` ni el build contiene `sb_secret_` ni `service_role`; solo se permite `VITE_SUPABASE_PUBLISHABLE_KEY`. **Mutación:** pegar `sb_secret_x` en un archivo de `src/`.
- [x] T040 [MIN] [P] [Paso 8] **Rojo:** `frontend/src/busqueda/NuevaBusqueda.test.tsx`, los 6 tests de spec:251-257. **Mutación:** habilitar Buscar comparando el estimado en lugar del máximo; no invalidar la vista previa al cambiar un filtro.
- [x] T041 [MIN] [P] [Paso 8] **Rojo:** `frontend/src/tablero/Tablero.test.tsx`:
  - los 6 de spec:259-268. **Mutación:** formatear `null` como `0`; un texto de atribución hardcodeado.
  - `::muestra_naturales_encontradas_no_contactables`. **viene de 011 (D7)** (T048 de la 011). Tres casos, en es y en:
    - `26304` se muestra "26.304" en es y "26,304" en en, con el esperado calculado con `Intl.NumberFormat`;
    - `null` se muestra "—";
    - `cuenta_naturales: false` se muestra el texto i18n de "no aplica".

    **Mutación:** `valor ?? 0` → "0".
- [x] T042 [MIN] [Paso 8] **Verde:**
  - `acceso/`, `busqueda/`, `tablero/` (con la columna "Naturales (no contactables)" y sus claves en es y en, que **viene de 011 (D7)**, T049);
  - `api/cliente.ts`, `compartido/{SelectorIdioma,formato}`;
  - `App.tsx` con el router.

## Fase 10: E2E local (Paso 9) — recortable, segundo en el orden de corte

- [ ] T043 [Pulido] [Paso 9] **Rojo:** `frontend/e2e/busqueda.spec.ts::login_vista_previa_buscar_tablero`, con `backend/tests/stubs/servidor_fuentes.py` vía `CROMA_BASE_URL` y `OVERPASS_URL`. Nunca contra Railway. El stub sirve además `/auth/v1/token` y un JWKS firmado con una clave de prueba.
- [ ] T044 [Pulido] [Paso 9] **Verde:** el job de CI levanta api, web, Postgres y el stub.

## Fase 11: Cola de revisión (Paso 10) — recortable, primero en el orden de corte

- [ ] T045 [Pulido] [Paso 10] **Rojo (advisor, cumplimiento):** `backend/tests/integration/test_revision_dedup.py`:
  - `::test_fusionar_mueve_lead_fuentes_y_marca_absorbido`. **Mutación:** sin el `DELETE` de los `lead_fuentes` del absorbido.
  - `::test_superviviente_es_el_que_tiene_id_fiscal`. **Mutación:** sobrevive siempre `lead_a`.
  - `::test_fusionar_con_id_fiscal_distinto_da_409`. **Mutación:** sin el veto.
  - `::test_resolver_dos_veces_da_409`. **Mutación:** sin el filtro `estado='pendiente'`.
  - `::test_fusionar_cierra_las_otras_pendientes_del_absorbido[x_mayor|x_menor]`. **Mutación:** insertar `(superviviente, X)` sin `least`/`greatest` → viola el `CHECK` en `x_menor`.
  - `::test_revision_con_lead_ya_fusionado_da_409`. **Mutación:** no chequear `fusionado_en` de los dos leads.
  - `::test_cumplimiento_de_ambos_queda_intacto`. **Mutación:** borrar el `cumplimiento` del absorbido.
  - `::test_separar_no_toca_leads`. **Mutación:** `separar` llama a `aplicar_fusion`.
  - `::test_cola_no_expone_contacto`. **Mutación:** `SELECT leads.*` en el repo.
- [ ] T046 [Pulido] [Paso 10] **Verde:** `resolver_revision.py` y el router `dedup`.
- [ ] T047 [Pulido] [P] [Paso 10] **Rojo:** `frontend/src/dedup/ColaRevision.test.tsx::lista_pares_y_resuelve`. No está en la spec; lo suma el plan, porque la pantalla no puede quedar sin test (principio II). **Mutación:** el botón Fusionar manda `separar`. **Verde:** `dedup/ColaRevision.tsx`.

## Fase 12: Corrida real (Paso 11)

- [ ] T048 [Pulido] [Paso 11] Vista previa + Buscar contra Croma, avisada antes. Se anota el saldo antes y después (esperado: 1 request y 1 crédito), si viene `total` y el tiempo de ejecución (umbral de 30 s).

## Fase 13: Docs (Paso 12)

- [ ] T049 [MIN] [Paso 12] `docs/arquitectura-backend.md`: vistas, lote = búsqueda, auth y cómo se agrega una columna al tablero.
- [ ] T050 [MIN] [P] [Paso 12] `docs/arquitectura-frontend.md`: la estructura por feature, la regla de límites y cuándo algo pasa a `compartido/`.
- [ ] T051 [Pulido] [P] [Paso 12] La corrección de `docs/prd.md` §4: `croma_consulta` es de lote, y Overpass registra solo segundos. Además, `spec.md` se alinea con P5 y P8 una vez que el dueño las resuelva.

## Dependencias y paralelismo

**[MIN]**, en este orden:
- T001 → T002, T003, T004 → Fase 2 [MIN] (T005–T013).
- La Fase 2 [MIN] → T024–T027 y, en paralelo, T029–T030.
- T024–T027 y T029–T030 → T031–T033 → T034 → T035, T037–T041 → T042 → T049–T050.
- Sin la Fase 3, la 4 ni la 5: el [MIN] no usa `gasto_busqueda`, `contar`, `costo_maximo_llamada` ni palabras clave.

**Pulido**, sobre el [MIN] en verde (las de abajo valen también para él):
- T001 bloquea todo. T004 va antes de cualquier rojo de Python.
- Fase 2 → Fase 3 → Fase 4. La Fase 5 puede correr en paralelo con la Fase 4.
- Las Fases 4 y 5 → Fase 6 → T028.
- La Fase 7 solo necesita la Fase 2. Las Fases 6 y 7 → Fase 8 → Fase 9 → Fase 10.
- T045–T046 necesitan la Fase 8. T047 necesita además T034 (esqueletos del front) y T042 (cliente y router).
- T034 va antes de cualquier rojo del front.
- Se pueden correr en paralelo T017, T018 y T019; T022 con la Fase 4; T039, T040 y T041.

## Orden de corte (spec:499-506)

1. Fase 11 (cola de revisión).
2. Fase 10 (E2E).
3. T022–T023 (4b, palabras clave): pasan a la 010, junto con `test_filtradas_por_palabras_no_generan_lead_ni_cumplimiento` de T026.
4. `v_costo_por_canal` y `test_costo_por_canal`: pasan a la 007.
5. Cobertura por país y revisiones pendientes en el tablero.

**No se cortan:** los tests de vistas, la RLS de vistas y de `usuarios`, el contrato de `contar` (incluido `[datos_gov_co_rues]`), el tope con sus tres adaptadores, auth, ni los 6 tests de la D7 con su verde. Varios son Pulido: van después del [MIN], pero no se cortan.

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

## Estrategia: primero que funcione

**Flujo mínimo:** login → Nueva búsqueda → OSM (003) y datos.gov.co (011) devuelven leads → se guardan por tenant → se ven en el tablero.

**No se negocia en ninguna [MIN]:**
- rojo real por aserción;
- aislamiento por tenant (RLS y `security_invoker`);
- sin secretos;
- el rol `app_rt` intacto.

**Orden:** 002 [MIN] → 003 [MIN] → 011 [MIN] → 005 [MIN] → 005 Pulido.

**Cuenta:** 52 tareas: 33 [MIN] (24 parciales) y 19 Pulido.

**Qué se deja afuera del [MIN]:**
- **Croma:** la 002 deja su CLI "sin adaptadores" y Croma al final. Por eso van a Pulido T017, T048, la parametrización `[croma_supersociedades_co]` de T016 y `CROMA_BASE_URL`.
- **Costos que no hacen falta para ver leads:** CPL, prorrateo, desperdicio, evals, tope, `contar`, `costo_maximo_llamada` y `gasto_busqueda`. El invariante "todo adaptador escribe en `costos` antes de devolver" ya lo cumplen los adaptadores de la 003 y la 011, y la 005 [MIN] no suma operaciones de salida.
- **Tope de gasto — ACTUALIZADO (rama feature/005-croma-tope): el tope YA SE APLICA** (`EjecutarBorrador`: `TopeExcedido` antes de la transición y chequeo antes de cada llamada; `VistaPrevia`: `costo_maximo_usd` y `dentro_del_tope`), `costo_maximo_llamada` está en los tres adaptadores y `croma_supersociedades_co` entra a la API (solo con `CROMA_API_KEY`; sin ella queda `sin_implementacion`). Siguen afuera: `contar` y el estimado (T016, T018-T020), el conteo por fuente, **el caché de respuestas de Croma** (no hay repositorio de `fuente_cache`: cada consulta repetida gasta un crédito y un request de los ~100 diarios), paginación (solo página 1), `TOPE_MAXIMO_USD` (`limites_app`) y la corrida real T048 (es de Daniel, con costo avisado). Lo que sigue es el texto original de la decisión, ya cumplido:
- **Tope de gasto (decisión del advisor, 2026-10-18):** `tope_gasto_usd` se guarda pero **no se aplica** hasta que el tope esté verde (Pulido: `gasto_busqueda`, `contar`, `costo_maximo_llamada`). Mientras tanto: (1) ninguna fuente de pago (Croma) habilitada para la API; hoy `fuentes.yaml` marca `croma_supersociedades_co` y `croma_dian_trade_co` con `habilitado: true`, pero no tienen clase en `adaptadores/__init__.py`, así que `cargar_registro` las deja en `sin_implementacion` y no se arman ni gastan: **no cambiar el flag ni sumar un adaptador de Croma al catálogo sin traer antes el tope**; (2) la UI y la API no presentan `tope_gasto_usd` como si se aplicara.
- **Geografía (recorte declarado, 2026-10-18):** (1) los **municipios** quedan pendientes de correr `backend/scripts/geografia_co.py` con red (datos.gov.co da 403 desde el entorno de desarrollo): hoy `co.yaml` trae los 33 departamentos y cero municipios; (2) las **cámaras** de `camaras_co.yaml` son 4 de 58; el resto va en T054; (3) **consecuencia hoy en producción:** OSM no corre, porque necesita `ciudad` y la ciudad solo se puede elegir de un municipio del archivo; y datos.gov.co solo sirve en los departamentos 11 y 25 (con otros responde `criterio_no_soportado` y la búsqueda sigue sin esa fuente). Hasta que se corra el script, la búsqueda real solo encuentra leads de datos.gov.co en Bogotá y Cundinamarca.
- **Vista previa:** en el [MIN] crea el borrador y devuelve las fuentes seleccionadas y las descartadas con su motivo, sin conteos ni costos. Sin `contar` no hay operación de salida nueva, y Buscar no depende de un tope.

**Dos migraciones, una por PR:**
- la del [MIN]:
  - `busquedas`: el `CHECK` de estado (P1);
  - `usuarios` con RLS;
  - `tenant_de_usuario`;
  - `v_tablero_fuentes` reducida a `fuente`, `encontrados` y `unicos`, con fila `TOTAL`;
  - `v_atribuciones`;
  - el `DO` de `REVOKE`.
- la de Pulido: el resto de plan §Migración. `v_tablero_fuentes` suma sus columnas de costo al final con `CREATE OR REPLACE VIEW`, que acepta columnas nuevas al final y conserva las que ya están.

### Qué entra al [MIN] de cada tarea parcial

Lo que no figura acá va a Pulido.

| Tarea | Entra al [MIN] | Por qué (dudosas) |
|---|---|---|
| T004 | `FabricaFuentes`, `VerificadorToken`, `VistaPrevia`, `EjecutarBusqueda` y los routers | `contar`, `gasto_busqueda`, `costo_maximo_llamada` y `filtrar_por_palabras` no los usa el [MIN] |
| T005 | La migración [MIN] de arriba, con stubs, sin `security_invoker` y sin RLS en `usuarios` | `fusionado_en` es de la cola de dedup |
| T006 | Todo. La mutación pasa a ser "borrar `usuarios.auth_user_id` de `modelos.py`" | `fusionado_en` no está en el [MIN] |
| T007 | Dos tests: `::test_lead_de_dos_fuentes_cuenta_una_vez_en_total` y uno nuevo, `::test_encontrados_y_unicos_por_fuente` | El nuevo usa el fixture de spec:77-112 y asierta solo `fuente`, `encontrados` y `unicos`. **Mutación:** `unicos = count(*)` → osm 8 ≠ 7. Es el conteo que muestra el tablero, sin costos |
| T008 | Los cuerpos de `v_tablero_fuentes` reducida y de `v_atribuciones`, el `GRANT` y el `CHECK` de estado (P1) | |
| T009 | `[vista]` sobre las dos vistas [MIN], `::test_toda_vista_es_security_invoker` y `::test_usuarios_tiene_rls` | `::test_tenant_b_no_fusiona_con_lead_de_a` va con `fusionado_en` |
| T011 | `security_invoker` y la RLS de `usuarios` | La FK compuesta va con `fusionado_en` |
| T012 | `::test_app_rt_no_lee_usuarios_directo`, `::test_tenant_de_usuario_devuelve_solo_ese_usuario` y `::test_tenant_de_usuario_es_security_definer_con_search_path` | `fijar_idioma` y su test van a Pulido |
| T013 | Todo, menos `fijar_idioma` | |
| T024 | Tres tests: `::test_crea_busqueda_en_borrador_con_criterios`, la parte de motivos de `::test_conteo_por_fuente_y_motivo_de_las_descartadas` y `::test_ignorados_son_los_criterios_que_la_fuente_no_aplica_y_el_ciiu_traducido_no_cuenta` (P7) | La fábrica entra al [MIN] solo para leer `.meta` (sin `contar`): la vista previa necesita las fuentes para seleccionar, y las pide con el `lote_id` del borrador. **Mutación:** usar `crear_busqueda` de la 002 → estado `creada`; pedir las fuentes antes del borrador → `lote_id=None`; no copiar `ignoradas`; derivar `ignorados` sin sacar el `ciiu` traducido → OSM trae `ciiu` |
| T025 | `crear_borrador`, `obtener_borrador` y `pasar_a_ejecutando` (P2) | `fijar_estimados` es de los conteos; `ignorados` (P7) entra en T024/T025 |
| T026 | `::test_solo_ejecuta_borrador` y `::test_usa_los_criterios_guardados` | Tope y palabras clave, a Pulido |
| T027 | `EjecutarBorrador` (comparte el núcleo con `EjecutarBusqueda`) sobre el borrador, con `lote_id = busqueda.id` y el estado final (P1) | Tope y `naturales_por_fuente`, a Pulido |
| T029 | Todo, menos `::test_fijar_idioma_persiste` y `::test_fijar_idioma_invalido_da_422` | `::test_usuarios_me_devuelve_idioma` queda: `elegirIdioma` (T037) lo usa |
| T030 | Todo, menos `PATCH /usuarios/me` | |
| T031 | Siete tests: `::test_tenant_sale_del_token_no_del_body`, `::test_tenant_b_no_ejecuta_busqueda_de_a`, `::test_ejecutar_dos_veces_da_409`, `::test_validacion[caso]` (sin los casos de tope), `::test_vista_previa_devuelve_motivos_como_codigo`, `::test_actividades_trae_ambos_nombres` y `::test_tablero_atribucion_solo_de_fuentes_presentes[caso]`. Más uno nuevo: `::test_tablero_devuelve_encontrados_y_unicos_del_tenant` | El nuevo siembra leads en A y en B, y como A asierta que salen sus filas y la `TOTAL`. **Mutación:** serializar `unicos` desde `encontrados`. La atribución entra porque ODbL la exige al mostrar datos de OSM. Las actividades entran porque sin ellas el formulario no elige CIIU |
| T032 | Los routers `busquedas`, `tablero` (reducido) y `actividades`, `repositorio_tablero.py`, y `nombre_es`/`nombre_en` en `actividades.yaml` | `limites_app` (P11) es del tope, y naturales (D7) va a Pulido |
| T034 | Todo, menos el esqueleto de `ColaRevision` | |
| T035 | Solo `::el_repo_no_tiene_violaciones`, con la regla `i18next/no-literal-string` | Es la guarda de es/en sobre el repo real (spec:249), y el es/en es constitucional. Los límites entre features (`boundaries`) van a Pulido con T036 |
| T039 | `api/cliente.test.ts::un_401_lleva_al_login_y_borra_el_token` | El selector de idioma va con `fijar_idioma` |
| T040 | Tres tests: `::buscar_deshabilitado_si_ninguna_fuente_cubre`, `::cambiar_un_filtro_invalida_la_vista_previa` y uno nuevo, `::buscar_ejecuta_y_lleva_al_tablero` | El nuevo es el paso "Nueva búsqueda dispara la búsqueda". **Mutación:** Buscar sin `POST /busquedas/{id}/ejecutar`, o sin navegar a `/tablero` |
| T041 | Dos tests: `::muestra_atribucion_de_las_fuentes_presentes[caso]` y uno nuevo, `::muestra_encontrados_y_unicos_por_fuente` | **Mutación:** pintar `encontrados` en la columna de únicos |
| T042 | `acceso/`, `busqueda/` y `tablero/` (sin las columnas de costo ni de naturales), `api/cliente.ts`, `compartido/formato` y `App.tsx` | `SelectorIdioma` va con `fijar_idioma` |
| T049 | Lote = búsqueda, auth y el tablero [MIN] | Documentación viva (constitución): se documenta lo que se construye, en el mismo cambio |
| T050 | La estructura por feature | Lo mismo |

Las dudosas que quedan en Pulido son tres:
- **T043–T044 (E2E):** el stub actual sirve Croma, y el flujo [MIN] ya lo cubren los tests de API (T031) y Vitest (T040–T041). El E2E del flujo principal entra primero en Pulido.
- **T036 (`boundaries`):** la estructura por feature se respeta a mano en el [MIN]. La guarda automática entra en Pulido.
- **T028:** prueba el lote de la vista previa, que en el [MIN] no gasta. El `lote_id = busqueda_id` de la ejecución ya lo prueba la 002 (T038).

### Qué P bloquea qué tarea [MIN]

- **P1 (estados):**
  - T005 y T008, por el `CHECK`;
  - T024 y T025, porque crean en `borrador`;
  - T026 y T027, por `pasar_a_ejecutando` y el estado final. El estado final choca con la 002: T039 de la 002 cierra en `terminada` o en `con_errores`.
- **P2 (métodos de borrador):** T024–T027.
- **P4:** no bloquea ninguna [MIN]. Bloquea T016–T020, que son Pulido.

### Qué necesita la 005 [MIN] de las otras slices

Los IDs de la 002 son los `[MIN]` de su tasks.md. Los de la 003 (47b35b9) y la 011 (c64c5f8) son los de su tasks.md actual: todavía no marcaron `[MIN]`, así que hay que cruzarlos cuando lo hagan.

- **002:**
  - T007: puertos, `MetaFuente` y `RegistroCostos`;
  - T010: `supabase_simulado.sql`, para T012;
  - T011, T014 y T019: la 0002, con `busquedas.creado_en`, `leads_tenant_id_id_key`, RLS y `modelos.py`, para T005, T006 y T008;
  - T012–T013: drift, para T006;
  - T016: la unidad de trabajo, para T009 y T031;
  - T017: `test_rls.py`, que extiende T009;
  - T018: `test_privilegios_supabase.py`, que extiende T010;
  - T021: `repositorio_leads.py`, al que T025 le suma los métodos de borrador;
  - T025: `postgres_costos.py`;
  - T038–T039: `EjecutarBusqueda` con `lote_id = busqueda_id`, que es la base de T026–T027.

  La CLI de la 002 queda "sin adaptadores" y Croma al final, así que nada [MIN] de la 005 depende de Croma.
- **003:**
  - T013: `actividades.yaml`, para T032;
  - T015 y T016b: `seleccionar_fuentes`, para T024;
  - T018 y T026: `Cifrador`, y el repo que cifra contacto al persistir;
  - T038–T044 y T048: el adaptador OSM, en el catálogo;
  - T051: `EjecutarBusqueda` con dedup y `cumplimiento`.

  Si la 003 deja el dedup difuso (T028–T036) fuera de su [MIN], T051 tiene que seguir escribiendo `cumplimiento` por lead nuevo.
- **011:**
  - T012–T018: el adaptador con el filtro de jurídicas;
  - T020: los campos aditivos;
  - T024 y T028–T030: el mapeo y los intentos con su costo;
  - T034: `settings`;
  - T040: el alta en el catálogo y en `fuentes.yaml`.

  Su `contar` (T035) y `naturales_por_fuente` (T041–T044) son del Pulido de la 005.
