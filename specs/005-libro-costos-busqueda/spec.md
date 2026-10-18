# Spec 005 — Libro de costos, CPL por fuente y formulario "Nueva búsqueda"

**Slice:** 005 · **Rama:** `feature/005-libro-costos-busqueda` · **Tiempo:** sábado PM (≤ 5 h)
**Depende de:** 002 (puerto, `costos`, `busquedas`), 003 (OSM, `revision_dedup`), 004 (filas `fuente='evals'` que hay que excluir). **Desbloquea:** 006 (`v_leads_icp` con encaje), 007 (`costo_por_respuesta` sobre el mismo fixture), 008 (CPQL), 010 (las puertas A y B prellenan este formulario).

> Con este slice ya hay demo mostrable (PRD §9): se elige un ICP, se ve cuánto hay y cuánto cuesta antes de gastar, se busca, y el tablero muestra el CPL por fuente.

## Para quién
- **La pyme usuaria (o Dapta operando por ella):** con la puerta C arma un ICP con filtros, ve por fuente cuántas empresas coinciden y cuánto va a costar, pone un tope de gasto y recién ahí busca.
- **El jurado y quien decide en Dapta:** el tablero muestra qué fuente trae leads más baratos, con el costo a valor de lista y el real (tier gratis), el desperdicio de cada fuente y el gasto de evals aparte.
- **El equipo:** las fórmulas viven en vistas SQL, en un solo lugar. 006, 007 y 008 agregan columnas sobre las mismas vistas y el mismo fixture.

## Qué hace
- **Vistas SQL del libro:** costo lista y real, prorrateo de lote por fuente, desperdicio, costo por lead, CPL por fuente, costo por canal y costo de evals aparte.
- **`lote_id` = `busquedas.id`:** formaliza el "lote de la corrida" del 002 y el 003.
- **`contar()` en el puerto `FuenteDescubrimiento`:** sirve para la vista previa con costo estimado.
- **Tope de gasto por búsqueda,** a valor de lista.
- **Auth mínima con Supabase Auth:** el front inicia sesión con Supabase, la API verifica el access token, y el tenant sale de la tabla `usuarios` por el `sub`. Llega con el primer endpoint que gasta créditos, como prometió el 002.
- **Endpoints HTTP** de vista previa, ejecución, tablero y cola de revisión de dedup.
- **Front:** login, formulario "Nueva búsqueda" y tablero por fuente.
- **Pantalla de la cola de revisión de dedup,** que prometió el 003. Es la última tarea y se puede recortar.

## Puertos y adaptadores que toca (`config/fuentes.yaml`)
- **`FuenteDescubrimiento`** suma `contar(criterios) -> int | None`, con contrato propio. Lo implementa toda fuente del catálogo:
  - **`fuentes_descubrimiento.croma_supersociedades_co`** (`habilitado: true`): `contar` hace la **misma** request de la página 1 de `buscar` (`per_page=100`), lee `total` y guarda la respuesta en `fuente_cache` con la misma clave. Después `buscar(pagina=1)` sale del caché, así que vista previa + Buscar = 1 request y 1 crédito. Este slice usa por primera vez el filtro `ingresos_min` (tamaño).
  - **`fuentes_descubrimiento.osm_overpass`** (`habilitado: true`): `contar` manda la misma query del 003 con `out count;` en lugar de `out center tags 500;`, y registra sus segundos como `overpass_query`.
  - Si `croma_dian_trade_co` se implementó en el 003, la suite de contrato la toma sola. Si no, sigue en `sin_implementacion`.
- **`limites.croma_requests_por_24h`** y **`limites.croma_creditos_gratis_mes`:** la vista previa muestra cuánto queda de cada uno.
- **`RegistroCostos` ← `postgres_costos`** suma `gasto_busqueda(busqueda_id) -> Decimal`: la Σ a valor de lista de las filas con `lote_id = busqueda_id`.
- **Secciones que no se cargan:** `enriquecedores`, `canales_contacto`, `calificadores` y `clasificadores` siguen sin cargarse. `canal_preferido` se valida contra `canales_contacto.*.habilitado` leyendo el YAML, sin instanciar adaptadores.

## Skills que aplican
- `libro-costos`: tipos `croma_consulta` y `overpass_query`, `gratis`, atribución, prorrateo, desperdicio, fórmulas, "sin dato" y fixture de 10 leads.
- `fuentes-publicas`:
  - atribución en el pie del tablero, solo de las fuentes que aportaron leads: "© OpenStreetMap contributors" (OSM, ODbL) y "Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)" (011);
  - Croma no se redistribuye: la API no expone `fuente_cache` ni respuestas crudas, solo conteos, costos y los leads del propio tenant.
- `cumplimiento-datos`:
  - el formulario no pide ni muestra contacto;
  - la cola de dedup no expone teléfono ni email;
  - fusionar no toca `cumplimiento`.
- `slice-tdd`.

## Evals
Ninguno: este slice no usa IA. La medición es el test de fórmulas, con números calculados a mano (abajo). El slice separa el costo de evals del 004 para que no ensucie el CPL: `fuente='evals'` va a `v_costo_evals` y a ninguna otra vista.

## Flujo principal
1. **Login (Supabase Auth):** el front inicia sesión con `supabase-js` (email + contraseña; P15 pendiente) y manda el access token como `Authorization: Bearer`. `GET /usuarios/me` devuelve `idioma_usuario` (la elección guardada, o `null`) e `idioma_tenant`; el front los usa para `elegirIdioma`. No hay `POST /auth/sesion` ni clave propia.
2. **Formulario "Nueva búsqueda" (puerta C):**
   - filtros: país · actividad (CIIU) · departamento o ciudad · tamaño (`ingresos_min`) · palabras clave · exclusiones;
   - formulario común: canal preferido · tope de gasto (USD) · mensaje base.
3. **Vista previa:** `POST /busquedas/vista-previa`.
   - Crea una fila en `busquedas` con `estado='borrador'` y los criterios **congelados**.
   - Corre `seleccionar_fuentes` del 002/003 y llama `contar` en cada fuente seleccionada.
   - Responde:
     - por fuente: `conteo` (o `null` + `motivo`), `ignorados` y `truncado`;
     - las fuentes descartadas, con su motivo (`pais`, `sin_mapeo_actividad`, `sin_geografia`);
     - `costo_vista_previa_usd` (real, desde el libro), `costo_estimado_usd` (lo esperable) y `costo_maximo_usd` (la cota alta);
     - créditos Croma restantes del mes y requests restantes en 24 h;
     - `dentro_del_tope` = `costo_maximo_usd ≤ tope_gasto_usd`.
   - El conteo es **antes** de palabras clave y exclusiones, y la pantalla lo dice.
4. **Buscar:** `POST /busquedas/{id}/ejecutar`, sin body. Usa los criterios guardados.
   - Si la búsqueda no está en `borrador` → 409. Si `costo_maximo_usd > tope_gasto_usd` → 409 y no corre nada.
   - Si pasa, `EjecutarBusqueda` del 002/003 corre con `lote_id = busqueda.id`:
     - antes de llamar a cada fuente, chequea `gasto_busqueda + costo_maximo_llamada(fuente) ≤ tope`; si no da, no la llama y la búsqueda termina en `tope_alcanzado`;
     - las empresas pasan por el post-filtro de palabras clave y exclusiones **antes** de persistir: una empresa filtrada no genera lead ni `cumplimiento`, pero lo que costó traerla queda en el lote;
     - estado final: `completada` | `tope_alcanzado` | `error`.
   - Responde encontrados · únicos · nuevos · en revisión · gasto lista y real.
5. **Tablero:** `GET /tablero/fuentes` devuelve las filas de `v_tablero_fuentes`, la fila TOTAL, el costo de evals, la cobertura por país (sale del registro: qué fuentes cubren cada país), las revisiones pendientes y `atribuciones` (las filas de `v_atribuciones`: una por fuente que aportó leads, con texto y enlace). El front solo formatea.
6. **Cola de revisión:** `GET /dedup/revision` lista los pares pendientes (nombre, ciudad, fuentes, similitud). `POST /dedup/revision/{id} {accion: fusionar|separar}` los resuelve.

## Terminado cuando (tests que hoy fallan)

**Fórmulas** (`backend/tests/integration/test_vistas_costos.py`, Postgres real con rol `app_rt`; el fixture se siembra con `postgres`)

Fixture: 10 leads A–J, 2 fuentes (`croma_supersociedades_co` = **cs**, `osm_overpass` = **osm**), 2 canales. Las tarifas son sintéticas y redondas: la vista no lee `tarifas.yaml`.

| Fila de `costos` | lote | fuente | lead | canal | unidades × costo_unitario | gratis |
|---|---|---|---|---|---|---|
| 1 | L1 | cs | — | — | 1 × 0.40 | true |
| 2 | L1 | cs | — | — | 1 × 0.40 | false |
| 3 | L1 | osm | — | — | 3 × 0.10 | false |
| 4 | L1 | NULL | — | — | 1 × 0.07 | false |
| 5 | L2 | cs | — | — | 1 × 0.50 | false |
| 6 | L2 | osm | — | — | 4 × 0.20 | false |
| 7 | — | cs | A | email | 1 × 0.05 | false |
| 8 | — | osm | G | whatsapp | 1 × 0.30 | false |
| 9 | E1 | evals | — | — | 1 × 1.00 | false |

`lead_fuentes`:
- L1: cs → A, B, C, D; osm → C, E, F;
- L2: cs → ninguno; osm → C, G, H, I, J.

C aparece en las dos fuentes, y dos veces en osm.

Resultados calculados a mano:

| fuente | encontrados | únicos (= ICP en 005) | costo lista | costo real | desperdicio lista/real | CPL lista | CPL real |
|---|---|---|---|---|---|---|---|
| cs | 4 | 4 | 1.35 | 0.95 | 0.50 / 0.50 | 0.3375 | 0.2375 |
| osm | 8 | 7 | 1.40 | 1.40 | 0 / 0 | 0.20 | 0.20 |
| sin_atribuir | 0 | 0 | 0.07 | 0.07 | 0.07 / 0.07 | NULL | NULL |
| **TOTAL** | 12 | **10** | 2.82 | 2.42 | 0.57 / 0.57 | 0.282 | 0.242 |

Costo por lead (lista/real):
- A·cs = 0.25 / 0.15;
- B·cs = D·cs = 0.20 / 0.10;
- C·cs = 0.20 / 0.10 y C·osm = 0.26 / 0.26;
- E·osm = F·osm = 0.10 / 0.10;
- G·osm = 0.46 / 0.46;
- H·osm = I·osm = J·osm = 0.16 / 0.16.

Costo por canal: email 0.05, whatsapp 0.30. Costo de evals: 1.00.

- `::test_cpl_por_fuente_fixture_10_leads`: `v_tablero_fuentes` da exactamente la tabla de arriba (`numeric`, comparación exacta).
- `::test_costo_por_lead_conserva_el_total`: para cada fuente, Σ `v_costo_por_lead` + Σ `v_desperdicio` == Σ costos de la fuente, en lista y en real. La comparación es exacta porque el fixture divide exacto. Con divisores como 3, `numeric` corta en 20 decimales y la conservación vale con tolerancia 1e-9. Las vistas no redondean: solo redondea el front, al mostrar.
- `::test_lote_sin_leads_es_desperdicio`: la fila 5 aparece en `v_desperdicio(cs, L2)` y no se reparte entre los leads de L1.
- `::test_prorrateo_es_por_lote_y_fuente`: el costo osm de L2 se reparte entre los 5 leads osm de L2 (0.16), no entre los 8 leads de L2 ni entre los de L1.
- `::test_lead_de_dos_fuentes_cuenta_una_vez_en_total`: C cuenta en `únicos` de cs y de osm, y una sola vez en el TOTAL (10, no 11).
- `::test_evals_excluido_y_aparte`: la fila 9 no aparece en ninguna vista salvo en `v_costo_evals` (1.00), y el TOTAL no la incluye.
- `::test_fuente_nula_es_sin_atribuir`: la fila 4 da la fila `sin_atribuir`, visible y con CPL NULL.
- `::test_divisor_cero_es_null`: CPL NULL, nunca 0 ni error de división.
- `::test_costo_por_canal`: `v_costo_por_canal` da email 0.05 y whatsapp 0.30.
- `::test_fila_con_lote_y_lead_va_al_lead`: se agrega la fila L1 · cs · lead B · 1 × 0.05. B pasa a 0.25 / 0.15, A, C y D no cambian, y `v_prorrateo` de (L1, cs) sigue en Σ parte = 0.80 / 0.40, 0.20 / 0.10 por lead. Con esto se prueba la regla: lo que define el prorrateo es `lead_id IS NULL`, no `lote_id`. La 006 cae en este caso.
- `::test_lead_fusionado_no_cuenta`: si se marca `H.fusionado_en = G` y se mueven sus `lead_fuentes`, osm queda con únicos = 6 y encontrados = 7, y el prorrateo de L2 pasa a 0.20 por lead (4 leads). El CPL de osm no se asierta exacto, porque 1.40/6 es periódico. Es el comportamiento buscado: el CPL se recalcula con los leads reales.

**Aislamiento y privilegios de las vistas**
- `backend/tests/integration/test_rls.py::test_tenant_b_no_accede_a_datos_de_a[vista]`, sobre cada `v_*`: con datos solo de A, el tenant B ve 0 filas. Control positivo en el mismo test: como A, cada vista devuelve ≥ 1 fila. Si no, el 0 de B no prueba nada. Por eso la siembra de A trae `costos`, leads y una `lead_fuentes` de `osm_overpass`; sin ella, `v_atribuciones` da 0 filas a cualquiera. Esto exige `security_invoker`: una vista común corre con los permisos de su dueño, `postgres`, que es dueño de las tablas, así que la RLS no le aplica.
- `::test_toda_vista_es_security_invoker`: toda vista de `pg_class` en `public` tiene `security_invoker=true` en `reloptions`. Sale del catálogo, así que una vista nueva entra sola.
- `test_rls.py::test_usuarios_tiene_rls`: en `pg_class`, `usuarios` tiene `relrowsecurity = true` y una política por `tenant_id` en `pg_policies`. `usuarios` **no** entra a la lista fija de `test_tenant_b_no_accede_a_datos_de_a[tabla]` del 002: `app_rt` no tiene privilegios sobre ella, así que el test daría `permission denied` y no probaría RLS. El aislamiento por rol lo cubre `test_app_rt_no_lee_usuarios_directo`, y el de RLS, este test.
- `test_rls.py::test_tenant_b_no_accede_a_datos_de_a[vista]`: B también ve 0 filas en la fila `TOTAL`, que solo existe si hay datos (`HAVING count(*) > 0`).
- `test_privilegios_supabase.py::test_anon_y_authenticated_sin_privilegios`: la lista suma `pg_views WHERE schemaname='public'`, y el assert previo exige que esté `v_tablero_fuentes`. `usuarios` entra sola por `pg_tables`.
- `backend/tests/integration/test_usuarios_repo.py`:
  - `::test_app_rt_no_lee_usuarios_directo`: un `SELECT`, INSERT, UPDATE o DELETE de `app_rt` sobre `usuarios` falla por privilegios;
  - `::test_tenant_de_usuario_devuelve_solo_ese_usuario`: con usuarios de 2 tenants, `tenant_de_usuario(<auth_user_id de A>)` devuelve 1 fila (`tenant_id` de A, `idioma_usuario`, `idioma_tenant`), y un uuid inexistente devuelve 0;
  - `backend/tests/unit/acceso/test_verificar_token.py::test_token_valido_devuelve_sub` y `::test_token_invalido_lanza[caso]` (sin red: par EC P-256 generado en el test y JWKS local). Casos inválidos: vencido, sin `exp`, sin `sub`, `aud` distinto, `iss` distinto, firmado con otra clave, `alg=none`, HS256 firmado con la clave pública como secreto (confusión de algoritmo) y `kid` ausente del JWKS;
  - `::test_fijar_idioma_no_cruza_tenants` (Pulido): control positivo: con `app.tenant_id` de A, `fijar_idioma(<auth_user_id de A>, 'en')` modifica 1 fila. Después, con `app.tenant_id` de B, `fijar_idioma(<auth_user_id de A>, 'en')` modifica 0 filas y el `idioma` de A no cambia;
  - `::test_funcion_es_security_definer_con_search_path[tenant_de_usuario|fijar_idioma]`: en `pg_proc`, `prosecdef = true`, `proconfig` contiene `search_path=` y `has_function_privilege` da `app_rt` sí y `anon`/`authenticated` no. Para que no nazca verde por la razón equivocada, `supabase_simulado.sql` (002) suma `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated`, que es lo que hace Supabase real. Sin el `REVOKE` de la 0004, el test falla.

**Libro y lote** (`backend/tests/integration/test_costos_repo.py`)
- `::test_gasto_busqueda_suma_lista_del_lote`: con filas `gratis` true y false en el lote, y filas de otro lote, `gasto_busqueda` da la Σ a valor de lista solo de su lote.
- `::test_costos_de_descubrimiento_llevan_lote_de_la_busqueda`: vista previa + ejecutar con transportes falsos dejan todas las filas con `lead_id IS NULL` con `lote_id = busqueda.id`. La CLI del 002 cumple lo mismo.

**Contrato del puerto** (`backend/tests/contratos/test_fuente_descubrimiento.py`, parametrizado sobre el catálogo)
- `::test_contar_registra_costo_antes_de_devolver[…]`.
- `::test_contar_devuelve_entero_no_negativo_o_none[…]`.
- `::test_contar_rechaza_criterio_no_soportado[…]`: lanza `CriterioNoSoportado` y no hace ningún request.
- `backend/tests/unit/descubrimiento/test_datos_gov_co.py::test_contar_segunda_llamada_sale_del_cache`: la 011 saca `contar` de su discriminador de caché (`tipo: filas|naturales`) y la 005 lo suma como `tipo: contar`. La segunda llamada a `contar` con los mismos criterios no hace request ni escribe costo.

**Adaptadores**
- `backend/tests/unit/descubrimiento/test_croma_supersociedades.py`:
  - `::test_contar_lee_total_de_la_pagina_1`, con la fixture sintética;
  - `::test_contar_y_buscar_hacen_una_sola_request`: `contar` y después `buscar(pagina=1)` con los mismos criterios dan 1 request y 1 fila en el registro falso;
  - `::test_ingresos_min_se_envia_como_filtro`.
- `backend/tests/unit/descubrimiento/test_osm_overpass.py`:
  - `::test_contar_usa_out_count`: el body lleva `out count;` y no `out center tags`, y se lee `elements[0].tags.total`;
  - `::test_contar_registra_segundos`: igual que `buscar` en el 003, sin contar las esperas.

**Selección y post-filtro** (unit, sin DB)
- `backend/tests/unit/descubrimiento/test_seleccion.py::test_tamano_es_refinamiento_no_requisito`: con `ingresos_min` en los criterios, Croma lo recibe y OSM queda seleccionada con `ingresos_min` en `ignorados`. No se descarta.
- `backend/tests/unit/descubrimiento/test_palabras_clave.py`:
  - `::test_coincide_por_token_normalizado`: la palabra clave `"Panadería"` matchea `"PANADERIA LA ESQUINA S.A.S."`; `"pan"` no matchea `"panaderia"`;
  - `::test_exclusion_gana_sobre_palabra_clave`: palabra clave `"panaderia"` y exclusión `"industrial"` dejan afuera `"PANADERIA INDUSTRIAL DEL VALLE"` y pasan `"PANADERIA LA ESQUINA"`;
  - `::test_palabra_clave_de_varios_tokens_exige_todos`: `"pan integral"` matchea `"PAN INTEGRAL Y MAS"` y no matchea `"PAN DE BONO"`;
  - `::test_sin_palabras_ni_exclusiones_pasa_todo`.

**Vista previa y ejecución** (unit, con fuentes y repos falsos)
- `backend/tests/unit/descubrimiento/test_vista_previa.py`:
  - `::test_conteo_por_fuente_y_motivo_de_las_descartadas`: con `pais=PE`, OSM trae su conteo y cs aparece descartada con `motivo='pais'`;
  - `::test_crea_busqueda_en_borrador_con_criterios`;
  - `::test_fuente_no_disponible_da_conteo_null_y_sigue`: `FuenteNoDisponible` en OSM da `conteo=None`, `motivo='no_disponible'`, y cs igual devuelve su conteo;
  - `::test_limite_agotado_da_conteo_null`: `LimiteFuenteAgotado` da `motivo='limite_agotado'`;
  - `::test_costo_estimado_suma_lo_gastado_y_lo_que_falta`: lo gastado en la vista previa sale del libro falso, y lo que falta es 0 créditos de cs (la página 1 ya está en caché) más los segundos del `contar` de OSM × `computo_seg_usd`;
  - `::test_costo_maximo_suma_costo_maximo_llamada_de_cada_fuente`: con cs + OSM seleccionadas, da lo gastado + 1 crédito × tarifa + 2 × 30 s × `computo_seg_usd`, y `dentro_del_tope` es false con un tope de un centavo menos. Un segundo caso con cs + OSM + `datos_gov_co_rues` suma además 2 × 2 × 30 s × `computo_seg_usd`: si falta, el tope se calcula sin ese adaptador y nadie lo nota;
  - `::test_reporta_creditos_y_requests_restantes`: con 37 requests en 24 h y 1.212 créditos usados en el mes en el libro falso, devuelve `requests_restantes_24h = 63` y `creditos_restantes_mes = 288`.
- `backend/tests/unit/descubrimiento/test_ejecutar_con_tope.py`:
  - `::test_no_ejecuta_si_costo_maximo_supera_tope`: lanza `TopeExcedido`, 0 requests, y la búsqueda sigue en `borrador`;
  - `::test_corta_antes_de_la_llamada_que_pasaria_el_tope`: el gasto se infla en el libro falso entre la vista previa y la ejecución (defensa en profundidad). Con eso, el tope alcanza para cs y no para OSM: OSM no se llama, el estado queda en `tope_alcanzado` y los leads de cs quedan guardados;
  - `::test_solo_ejecuta_borrador`: la segunda ejecución lanza `BusquedaYaEjecutada`;
  - `::test_usa_los_criterios_guardados`: se guarda un borrador con `ciiu=1081` y la fuente falsa recibe exactamente `{pais: CO, ciiu: 1081, departamento: …}` del borrador. `ejecutar` no acepta criterios, porque no tiene parámetro para eso;
  - `::test_filtradas_por_palabras_no_generan_lead_ni_cumplimiento`.
- El advisor revisa estos tests antes de aceptarlos: son de juicio sobre costos.

**API y auth** (`backend/tests/integration/test_api_busquedas.py` y `test_auth.py`, `TestClient` contra Postgres de prueba, transportes falsos)
- `test_auth.py` (el token lo firma una clave de prueba; el verificador recibe un JWKS local):
  - `::test_token_valido_resuelve_el_tenant_desde_usuarios`: un token con un claim `tenant_id` (o `user_metadata.tenant_id`) de B y un `sub` de un usuario de A actúa como A. El tenant sale de la base, no del token;
  - `::test_token_valido_sin_fila_en_usuarios_da_403`: cuerpo `sin_acceso`, y revocar (borrar la fila) corta el acceso con el mismo token;
  - `::test_sin_token_da_401[ruta]`: parametrizado sobre `app.routes`, menos `/health`. Una ruta nueva entra sola;
  - `::test_token_invalido_da_401[caso]`: los mismos casos del verificador, ahora por la API;
  - `::test_app_no_arranca_sin_auth_jwks_url_ni_issuer`, y `::test_jwks_inaccesible_da_503`;
  - `::test_docs_desactivadas`: `/docs`, `/redoc` y `/openapi.json` dan 404;
  - `::test_cors_solo_permite_web_origin`: un preflight desde `WEB_ORIGIN` recibe `Access-Control-Allow-Origin` con ese valor, y uno desde `https://otro.example` no recibe el header;
  - `::test_token_no_aparece_en_logs` (`caplog` durante un 401 y un 200);
  - `::test_usuarios_me_devuelve_idioma[caso]`: `GET /usuarios/me` con `usuarios.idioma='en'` y tenant `es` devuelve `idioma_usuario='en'` e `idioma_tenant='es'`; con `usuarios.idioma` NULL, `idioma_usuario` es `null`;
  - `::test_fijar_idioma_persiste` (Pulido): `PATCH /usuarios/me {idioma: 'en'}` da 204, y el `GET /usuarios/me` siguiente devuelve `idioma_usuario='en'`;
  - `::test_fijar_idioma_invalido_da_422[caso]`: `idioma` `'pt'` o `''`, y un body con `usuario_id` o `tenant_id` (`extra='forbid'`). El usuario sale del `sub` del token, nunca del body. El 401 sin token lo cubre `test_sin_token_da_401[ruta]`, que levanta la ruta nueva sola.
- `test_api_busquedas.py`:
  - `::test_tenant_sale_del_token_no_del_body`: un body con `tenant_id` da 422 (`extra='forbid'`), y la búsqueda creada sin ese campo tiene el tenant del token;
  - `::test_tenant_b_no_ejecuta_busqueda_de_a`: B ejecuta el `id` de A y recibe 404, y la búsqueda de A no cambia;
  - `::test_ejecutar_dos_veces_da_409`;
  - `::test_ejecutar_con_costo_maximo_sobre_tope_da_409`: el borrador queda en `borrador` y no hay filas nuevas en `costos`;
  - `::test_validacion[caso]` → 422 con: `ciiu` que no tiene 4 dígitos, país fuera del enum, `tope_gasto_usd` ≤ 0 o > `TOPE_MAXIMO_USD`, `mensaje_base` > 1000 caracteres, más de 10 palabras clave o alguna de más de 40 caracteres, y `canal_preferido` deshabilitado en el registro;
  - `::test_tablero_devuelve_null_para_cpl_sin_divisor`;
  - `::test_vista_previa_devuelve_motivos_como_codigo`: los motivos de fuente descartada y los errores de validación son códigos (`sin_mapeo_actividad`, nombre de la regla), nunca una frase;
  - `::test_actividades_trae_ambos_nombres`: `GET /actividades` devuelve `codigo`, `nombre_es` y `nombre_en` (que puede ser `null`) de cada entrada de `config/actividades.yaml`;
  - `::test_tablero_atribucion_solo_de_fuentes_presentes[caso]`: siembra `lead_fuentes` directo con `postgres` (no hace falta el adaptador de la 011) y compara `atribuciones` exacto y en orden, cada elemento `{fuente, texto, url}`:
    - `solo_osm` → solo `osm_overpass`, "© OpenStreetMap contributors", `https://www.openstreetmap.org/copyright`;
    - `osm_y_datos_gov` → `osm_overpass` y `datos_gov_co_rues`, "Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)", `https://creativecommons.org/licenses/by-sa/4.0/`;
    - `solo_croma` → `[]`;
    - `sin_leads` → `[]`.

**Cola de revisión** (`backend/tests/integration/test_revision_dedup.py`)
- `::test_fusionar_mueve_lead_fuentes_y_marca_absorbido`: el absorbido queda con `fusionado_en` = superviviente y sin `lead_fuentes`.
- `::test_superviviente_es_el_que_tiene_id_fiscal`: si ninguno lo tiene, sobrevive el más antiguo (`creado_en`).
- `::test_fusionar_con_id_fiscal_distinto_da_409`: es el veto del 003.
- `::test_resolver_dos_veces_da_409`: se resuelve con `SELECT … FOR UPDATE` sobre la fila de revisión.
- `::test_fusionar_cierra_las_otras_pendientes_del_absorbido`: H está en dos pendientes, H~G y H~X. Fusionar H→G deja H~X en `separado`, con `motivo='absorbido'`, y abre G~X en `pendiente`, salvo que ya exista o que G = X. G~X lleva el `busqueda_id` y la `similitud` de H~X (se asierta). Se parametriza con X > G y con X < G, para probar que `lead_a`/`lead_b` salen de `least`/`greatest` y no violan el `CHECK`.
- `::test_revision_con_lead_ya_fusionado_da_409`: se marca a mano `H.fusionado_en = G`, y resolver H~X con `fusionar` da 409. X conserva sus `lead_fuentes`.
- `::test_cumplimiento_de_ambos_queda_intacto`.
- `::test_separar_no_toca_leads`.
- `::test_cola_no_expone_contacto`: el JSON no tiene claves de teléfono ni de email, ni ningún `*_cifrado`.

**Arquitectura del front** (`frontend/tests/arquitectura/limites.test.ts`, con `// @vitest-environment node`, porque corre ESLint por su API de Node y no por el DOM). Es el mismo patrón que el canario de import-linter del 002:
- **El canario:** un directorio de `fs.mkdtempSync` con un `tsconfig.json` mínimo y estos archivos, **todos existentes** (un import a un archivo que no existe no resuelve, y boundaries lo ignora):
  - `src/busqueda/Algo.tsx`, `src/compartido/X.ts`, `src/api/cliente.ts`, `src/test/servidor.ts`;
  - `src/tablero/Usa.tsx`, que importa `../busqueda/Algo` **sin extensión**: así ejercita la resolución de `.tsx`, que es lo que tienen las features reales;
  - `src/compartido/Malo.ts`, que importa `../busqueda/Algo`;
  - `src/tablero/Prod.tsx`, que importa `../test/servidor`.

  Se lintea con `new ESLint({ cwd: tmp, overrideConfigFile: <ruta del eslint.config.js real> })`. Es la config real, no una copia: sin `overrideConfigFile`, ESLint busca la config desde el tmp y no la encuentra. Los patrones de elementos son relativos al final de la ruta (modo `folder`, el default de boundaries), no `mode: 'full'`, porque boundaries toma su raíz de `process.cwd()`, no del `cwd` de ESLint.
- `::detecta_feature_que_importa_otra_feature`: `tablero/Usa.tsx` tiene al menos un error con `ruleId === 'boundaries/element-types'`.
- `::detecta_compartido_que_importa_una_feature` y `::detecta_produccion_que_importa_test`: lo mismo para `compartido/Malo.ts` y `tablero/Prod.tsx`. Así nadie puede dejar esas dos direcciones en `allow` sin que se note.
- `::permite_importar_de_compartido_y_api`: el control positivo. `src/tablero/Bueno.tsx` importa `../compartido/X` y `../api/cliente` y da 0 errores. Prueba que la regla no es "prohibir todo". Un error de parseo no puede dejar verde a los negativos, porque trae `ruleId` null y ellos filtran por `boundaries/element-types`.
- `::import_sin_resolver_es_error`: `src/tablero/Roto.tsx` importa `../busqueda/NoExiste` y da error de `import/no-unresolved`, en `error` en la config. Sin esto, un resolver mal configurado deja todo en silencio.
- `::el_repo_no_tiene_violaciones`: ESLint sobre el `src/` real da 0 errores, **y** los `results` contienen `src/App.tsx` y `src/busqueda/NuevaBusqueda.tsx`. Si un glob no matchea o un `ignores` se come los `.tsx`, el test falla en lugar de pasar vacío.

Corre en el job de front de CI como parte de `npm test`, sin step aparte.

**Idiomas del front** (`frontend/tests/arquitectura/i18n.test.ts`, con `// @vitest-environment node`, el mismo patrón que `limites.test.ts`):
- `::es_y_en_tienen_las_mismas_claves`: las claves aplanadas (`a.b.c`) de `src/i18n/es.json` y `en.json` son el mismo conjunto, y ningún valor es `""`. El mensaje de falla lista las claves que faltan de cada lado. Un assert previo exige al menos las claves `motivos.sin_mapeo_actividad` y `acceso.ingresar`, para que dos archivos vacíos no pasen.
- `::detecta_texto_literal_en_jsx`: el canario. En el mismo tmp que `limites.test.ts`, `src/busqueda/Literal.tsx` con `<p>Hola</p>` da al menos un error con `ruleId === 'i18next/no-literal-string'`, con la config real (`overrideConfigFile`).
- `::detecta_texto_literal_en_atributo`: segundo canario, `<input placeholder="Buscar" />` da al menos un error de esa regla. `# [VALIDAR]` que `jsx-only` lo atrape; si no, se configura `jsx-attributes` hasta que el canario dé rojo con el texto y verde con `t(...)`.
- `::permite_texto_traducido`: el control positivo. `src/busqueda/Traducido.tsx` con `<p>{t('acceso.ingresar')}</p>` da 0 errores de esa regla.
- `frontend/src/i18n/elegirIdioma.test.ts::precedencia[caso]`, puro, sobre `elegirIdioma(languages, idiomaUsuario, idiomaTenant)`:
  - `['es-CO']`, elección guardada `en`, tenant `es` → `en`. La elección gana sobre el navegador y el tenant: este caso fija el orden;
  - `['es-CO']`, sin elección, tenant `en` → `es`. El navegador gana sobre el tenant;
  - `['fr']`, sin elección, tenant `en` → `en`. Sin navegador útil, vale el tenant;
  - `['fr']`, sin nada → `es`;
  - `['pt-BR', 'en-US']`, sin nada → `en`: corta el código regional y toma el primero que está en `{es, en}`.
- El repo real queda cubierto por `limites.test.ts::el_repo_no_tiene_violaciones`, que ya lintea `src/` con la config real: un literal en un componente lo pone en rojo.

**Front** (Vitest + Testing Library, con la API mockeada)
- `frontend/src/busqueda/NuevaBusqueda.test.tsx`:
  - `::muestra_conteo_y_motivo_por_fuente`;
  - `::aclara_que_el_conteo_es_antes_de_palabras_clave`;
  - `::buscar_deshabilitado_si_costo_maximo_supera_tope`: muestra el estimado y el máximo, y explica que se compara el máximo;
  - `::buscar_deshabilitado_si_ninguna_fuente_cubre`;
  - `::cambiar_un_filtro_invalida_la_vista_previa`: Buscar queda deshabilitado hasta una nueva vista previa;
  - `::cambia_idioma`: con `vi.spyOn(navigator, 'languages', 'get')` devolviendo `['es-CO']` (jsdom trae `['en-US']`) y la sesión con `idioma_usuario: null` e `idioma_tenant: 'es'`, arranca en es. Elegir English en el selector manda un solo `PATCH /usuarios/me` con body exacto `{idioma: 'en'}`, sin `usuario_id` ni `tenant_id`. El handler de MSW lo captura, y el test lo espera con `waitFor`. Además cambia las etiquetas al texto de `en.json`, el motivo `sin_mapeo_actividad` que vino como código, y el tope, que sale de `Intl.NumberFormat('en', {style: 'currency', currency: 'USD'})` (el test calcula lo esperado con `Intl`, no lo escribe a mano). La actividad muestra `nombre_en`, y la que tiene `nombre_en: null` muestra `nombre_es`. Al final, desmontar y `await i18n.changeLanguage('es')`: `i18next` es un singleton y sin eso seguiría en `en` por inercia, simulando una carga en frío. Después volver a montar la app con el mismo `sessionStorage` y el navegador todavía en `es-CO`: sigue en en. Eso prueba que la elección se guardó y que la app la lee al arrancar.
  - `Login.test.tsx::selector_sin_sesion_no_guarda`: en `/login`, elegir English cambia las etiquetas y no dispara ningún `PATCH`.
- `frontend/src/tablero/Tablero.test.tsx`:
  - `::cpl_null_se_muestra_sin_dato`: nunca `0` ni `∞`;
  - `::muestra_costo_lista_y_real`;
  - `::costo_de_evals_va_aparte`;
  - `::muestra_atribucion_de_las_fuentes_presentes[caso]`: el pie pinta un enlace por elemento de `atribuciones`, con el `texto` y el `href` de la API:
    - `ambas` → se ven "© OpenStreetMap contributors" (enlace a `/copyright`) y "Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)";
    - `solo_osm` → se ve la de OSM y no la de datos.gov.co;
    - `ninguna` → no hay atribución. Con este caso y el anterior, un texto hardcodeado en el front falla;
  - `::muestra_cobertura_por_pais`;
  - `::muestra_revisiones_pendientes`.
- `frontend/src/api/cliente.test.ts::un_401_lleva_al_login_y_borra_el_token`.

**E2E** (`frontend/e2e/busqueda.spec.ts::login_vista_previa_buscar_tablero`): login con Supabase Auth contra un stub local (`/auth/v1/token` y un JWKS firmado con una clave de prueba, en `servidor_fuentes.py`; nunca el proyecto real) con el usuario sembrado → formulario CO + CIIU 1081 + Bogotá → la vista previa muestra los conteos del stub (cs 3, osm 2) → Buscar → el tablero muestra 5 únicos y un CPL de cs que no es "sin dato". Corre en CI **local**, con api y web levantados en el runner, Postgres de servicio y un stub HTTP (`backend/tests/stubs/servidor_fuentes.py`) apuntado por `CROMA_BASE_URL` y `OVERPASS_URL`. Nunca corre contra Railway: gastaría créditos reales. El E2E del 001 contra Railway (health) sigue como está.

## Fuera del alcance
- **006:**
  - `v_leads_icp` filtrando por `encaje <> 'no_encaja'`;
  - las columnas "con teléfono" y "contactables";
  - los costos de enriquecimiento y a qué fuente se atribuyen cuando el lead tiene dos.
- **007:**
  - contactados, entregados, respondieron y bloqueos;
  - `costo_por_respuesta` (se extiende este mismo fixture);
  - la línea de tiempo de costos.
- **008:** calificados y CPQL, sobre el mismo fixture.
- **010:** puertas A y B. Prellenan este formulario y no lo reemplazan.
- **012:**
  - pantalla de cumplimiento;
  - rate limit del login y bloqueo por intentos: los da Supabase Auth, ya no se construyen;
  - rotación de las claves de firma: es de Supabase (JWKS).
- Paginación: más de la página 1 de Croma y más de 500 elementos de Overpass.
- Alta de usuarios por UI (va por script), roles y más de un usuario por tenant con permisos distintos.
- Monedas que no sean USD.
- Ejecución en background con polling (ver Decisiones técnicas).
- **Idiomas:** traducir la API (devuelve códigos), traducir los docs y portugués.

## Decisiones técnicas

**Dónde vive cada cosa:**
- **`app/modulos/descubrimiento/`:**
  - `dominio/palabras_clave.py` (puro, usa el normalizador del 003);
  - `aplicacion/vista_previa.py`, `aplicacion/ejecutar_busqueda.py` (con el tope) y `aplicacion/resolver_revision.py` (reusa la función `fusionar` del dominio del 003).
- **`app/modulos/tablero/infraestructura/persistencia/repositorio_tablero.py`:** solo lee vistas. Es un módulo sin dominio a propósito, porque la lógica vive en SQL (PRD §7).
- **`app/modulos/acceso/`:**
  - `dominio/`: el puerto `VerificadorToken` y `TokenInvalido`;
  - `infraestructura/verificador_jwks.py`: el adaptador con PyJWT y JWKS;
  - `infraestructura/persistencia/repositorio_usuarios.py`: llama a `tenant_de_usuario`.
- **`app/api/`:** los routers (adaptadores de entrada) y `sesion.py` (Bearer → `VerificadorToken` → `tenant_de_usuario(sub)` → dependencia `tenant_actual`).
- **`EXCLUIDOS`** de los tests de arquitectura suma `repositorio_tablero.py` y `repositorio_usuarios.py`, con la misma razón del 002: base propia, sin HTTP.

**Lote = búsqueda:**
- Toda operación de descubrimiento lleva `lote_id = busquedas.id`. Las operaciones de slices siguientes que gasten "por una búsqueda" llevan el mismo `lote_id`, para entrar al tope; si además tienen `lead_id`, se atribuyen al lead y no se prorratean (skill).
- `costos.lote_id` **no** tiene FK a `busquedas`, porque el lote de evals es la corrida del 004.
- **"Costo de cómputo", la promesa del 002:** acá es solo el `overpass_query` (segundos del request externo, 003). El cómputo propio de `EjecutarBusqueda` (CPU del api) no se mide en este slice. `# ponytail:` se agrega con un decorador de tiempo si el número de Railway lo justifica.
- **`croma_consulta` es de lote, no "al lead":** PRD §4 dice "al lead", pero una consulta de búsqueda trae 100 empresas y no se sabe de antemano cuáles van a ser leads. Se prorratea. Se corrige la tabla del PRD en este PR. Lo mismo pasa con "segundos + bytes" de Overpass: el 003 registra solo segundos, y la tabla se alinea.

**Vistas** (todas `WITH (security_invoker = true)`, PG ≥ 15; CI usa `postgres:16`):
- `v_costos`: `monto_lista = unidades × costo_unitario`, `monto_real = CASE WHEN gratis THEN 0 ELSE monto_lista END`, `fuente_ef = COALESCE(fuente, 'sin_atribuir')`. Filtra `fuente IS DISTINCT FROM 'evals'`.
- `v_costo_evals`: solo `fuente = 'evals'`, por lote.
- `v_leads_icp(lead_id, fuente, busqueda_id)`: `lead_fuentes` ⋈ `leads` con `fusionado_en IS NULL`. **Es la única definición de ICP:** la 006 le agrega el filtro de encaje y todo lo demás se mueve solo.
- `v_prorrateo(lote_id, fuente, lead_id, parte_lista, parte_real)`: las filas de lote (`lead_id IS NULL`), agrupadas por `(lote_id, fuente_ef)`, divididas por `COUNT(DISTINCT lead_id)` de `v_leads_icp` con `busqueda_id = lote_id` y la misma fuente.
- `v_desperdicio(fuente, lote_id, …)`: los grupos `(lote, fuente)` sin leads.
- `v_costo_por_lead(lead_id, fuente, costo_lista, costo_real)`: costo directo (`lead_id` no nulo, por la `fuente` de la fila) + prorrateo.
- `v_costo_por_canal(canal, …)`: las filas con `canal` no nulo.
- `v_tablero_fuentes`: por fuente y una fila `TOTAL` (con `HAVING count(*) > 0`: sin datos, no hay fila), con estas columnas:
  - `encontrados` = filas de `lead_fuentes`;
  - `unicos` = leads distintos;
  - `icp`;
  - costos lista y real;
  - desperdicio lista y real;
  - `cpl_lista` = costo_lista / NULLIF(icp, 0), e igual `cpl_real`.
- `v_atribuciones(fuente, texto, url, orden)`: un `VALUES` con las fuentes cuya licencia pide atribución, filtrado por `EXISTS` de al menos una fila en `lead_fuentes` del tenant con esa `fuente`:
  - `osm_overpass` → "© OpenStreetMap contributors" y `https://www.openstreetmap.org/copyright`, que es lo que pide la OSMF: el aviso más el enlace a `/copyright`;
  - `datos_gov_co_rues` → "Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)" y el enlace a la licencia;
  - Croma no lleva fila: no tiene licencia abierta que pida atribución, y no se redistribuye.
  - Sale de `lead_fuentes` y no de `cumplimiento`, porque un lead fusionado tiene una sola fila de cumplimiento (la de su origen) y las `lead_fuentes` de todas sus fuentes. Tampoco mira `habilitado`: una fuente desconectada que ya aportó leads sigue en la base y sigue debiendo atribución.
  - `# ponytail:` el mapa vive en la vista. Si se suma una tercera fuente con atribución, se mueve a una columna `atribucion` en `config/fuentes.yaml`.
- **El CPL incluye el desperdicio en el numerador:** el costo de adquirir leads incluye las búsquedas que no rindieron (fórmula de la skill: Σ costos(fuente)). Por eso el CPL no es el promedio de `v_costo_por_lead`, y el test de conservación cierra la cuenta.
- La API serializa `numeric` como string decimal y `NULL` como `null`. El front formatea; no calcula.

**Vista previa y costo estimado:**
- `costo_estimado_usd` = lo ya gastado por la vista previa (desde el libro, a valor de lista) + lo que falta para ejecutar.
- **Lo que falta para ejecutar:**
  - **cs:** 0 si la página 1 quedó en caché; si `contar` falló, 1 crédito × tarifa.
  - **OSM:** los segundos medidos en `contar` × `computo_seg_usd`. Es una **cota baja**: traer 500 elementos tarda más que contarlos.
- `costo_maximo_usd` = lo ya gastado + Σ `costo_maximo_llamada` de las fuentes seleccionadas (ver Tope). Es lo que se compara con el tope, así que una vista previa "dentro del tope" no puede terminar en `tope_alcanzado` salvo que el gasto cambie entre medio.
- Los dos se guardan en `busquedas` (`costo_estimado_usd` y `costo_maximo_usd`). El tablero de la búsqueda muestra el estimado contra el real.
- `# ponytail:` `fuente_cache` es global (002). Si un tenant B repite la consulta de A, la usa gratis y el costo queda en el lote de A. Con un solo tenant en el evento no importa. Con varios: caché por tenant, o prorrateo de la consulta entre los lotes que la usaron.
- Cada vista previa crea un borrador nuevo. Uno abandonado deja su costo como desperdicio de su fuente, que es lo honesto: esa consulta no produjo leads.
- **Los criterios quedan congelados en el borrador** y `ejecutar` no recibe body. Así no se puede previsualizar un ICP barato y ejecutar uno caro.

**Tope de gasto:**
- Se mide a valor de lista (conservador: el tier gratis se acaba en medio de una búsqueda).
- Antes de cada llamada a una fuente: `gasto_busqueda + costo_maximo_llamada ≤ tope`. `costo_maximo_llamada` lo declara cada adaptador en su `MetaFuente`:
  - **cs:** 1 crédito × tarifa, porque los intentos fallidos registran 0;
  - **OSM:** 2 intentos × 30 s (el timeout del cliente, 003) × `computo_seg_usd`;
  - **`datos_gov_co_rues`:** 2 requests × 2 intentos × 30 s × `computo_seg_usd` (la fórmula es de la 011: `specs/011-datos-gov-co/spec.md:230` en c64c5f8).
- `TOPE_MAXIMO_USD` (50) vive en `config/tarifas.yaml` en la sección `limites_app`.
- La CLI del 002 sigue sin tope: es de operador, local.
- `busquedas.estado` pasa a tener un `CHECK` ∈ `borrador`/`ejecutando`/`completada`/`tope_alcanzado`/`error`. La transición de `borrador` a `ejecutando` es un `UPDATE … WHERE estado='borrador'` que tiene que afectar 1 fila; si afecta 0, es 409. Eso cubre dos clics simultáneos.
- `# ponytail:` la ejecución es síncrona. Si en la corrida real pasa de 30 s, se mueve a background con polling de `estado`.

**Palabras clave y exclusiones:**
- Es un post-filtro puro sobre los tokens de `nombre_normalizado` (el normalizador del 003). Una palabra clave de varias palabras exige todos sus tokens.
- No hay substring a propósito: `"pan"` no debe traer `"panaderia"` ni `"empanadas"`.
- `# ponytail:` solo mira el nombre. Si hace falta mirar la actividad o la web, se agrega cuando haya un caso real.

**Auth (Supabase Auth, decisión del dueño 2026-10-18; detalle y alternativas en plan.md, "Auth con Supabase Auth"):**
- **Login:** lo hace Supabase Auth desde el front (`supabase-js`, email + contraseña; P15 pendiente). La API no ve ni guarda emails ni claves.
- **`usuarios`** (`auth_user_id uuid PRIMARY KEY` = `sub` del token, `tenant_id` FK, `idioma` NULL con `CHECK IN ('es','en')`, `creado_en`) tiene **RLS por `tenant_id`** (constitución III). **Sin FK a `auth.users`** (P16): en CI no existe el esquema `auth`. `app_rt` no tiene ningún privilegio sobre la tabla.
- **Verificación del token:** `PyJWT` con `PyJWKClient(AUTH_JWKS_URL)`, `algorithms=["ES256","RS256"]` (nunca HS256), `audience="authenticated"`, `issuer=AUTH_ISSUER` y `require: exp, sub, aud, iss`. La api no tiene secreto de firma ni `service_role` (P17). JWKS inaccesible: 503.
- **El tenant sale de la tabla, no del token.** Después de verificar, la API llama a `tenant_de_usuario(p_auth_user_id uuid)`:
  - `SECURITY DEFINER`, dueño `postgres`, `SET search_path = public, pg_temp`;
  - devuelve `tenant_id`, `usuarios.idioma` y `tenants.idioma` de **ese** usuario y nada más; 0 filas → 403 `sin_acceso`;
  - `REVOKE EXECUTE … FROM PUBLIC, anon, authenticated` y `GRANT EXECUTE` solo a `app_rt` (la 0004 trae su `DO` con el guard de `pg_roles` del 002; no toca la 0002);
  - así un `SELECT` de `app_rt` no puede volcar `usuarios` de otros tenants.
- **Revocar** es borrar la fila de `usuarios`.
- `fijar_idioma(p_auth_user_id uuid, p_idioma text)` (Pulido), mismo patrón, `UPDATE … WHERE auth_user_id = p_auth_user_id AND tenant_id = current_setting('app.tenant_id')::uuid`. `PATCH /usuarios/me` la llama con el `sub`.
- **Alta (paso humano):** el dueño crea el usuario en el panel de Supabase y `backend/scripts/crear_usuario.py --auth-user-id UUID --tenant UUID [--idioma es|en]` (URL de `postgres` por `getpass`) inserta la fila.
- **`/docs`, `/redoc` y `/openapi.json` desactivados** (`docs_url=None`, etc.). Así el test de 401 sobre `app.routes` no tiene excepciones escondidas.
- **Los modelos de entrada son `extra='forbid'`:** un `tenant_id` en el body es 422. La dependencia `tenant_actual` abre la unidad de trabajo con `SET LOCAL app.tenant_id` (002).
- **Sesión en el navegador:** la guarda `supabase-js` (almacenamiento del navegador). Sin cookies no hay CSRF. El riesgo es XSS: React escapa, no hay `dangerouslySetInnerHTML`, y `mensaje_base` se guarda y se muestra como texto plano. La CSP la revisa la 012.
- **CORS:** `allow_origins=[WEB_ORIGIN]`, sin `allow_credentials`.

**Cola de revisión (fusionar):**
- Sobrevive el lead que tiene `id_fiscal`; si ninguno lo tiene, el más antiguo. Así el `coalesce` nunca mueve un `id_fiscal` y no choca con UNIQUE `(tenant_id, pais, id_fiscal)`.
- Si los dos tienen `id_fiscal` distinto, es 409 (veto del 003).
- Todo va en una transacción:
  - `SELECT … FOR UPDATE` de la revisión, con `estado='pendiente'`, y `FOR UPDATE` de los dos leads, en orden de `id` para no hacer deadlock. Si alguno tiene `fusionado_en`, es 409;
  - `fusionar` del dominio del 003 (coalesce, el canal sube y nunca baja, `tipo_titular` sube);
  - `INSERT … SELECT` de los `lead_fuentes` del absorbido hacia el superviviente, con `ON CONFLICT DO NOTHING`, y después `DELETE` de los del absorbido;
  - `absorbido.fusionado_en = superviviente`;
  - la revisión pasa a `fusionado`;
  - las otras pendientes del absorbido pasan a `separado` con `motivo='absorbido'` (`revision_dedup` suma `motivo text NULL`), y se abre la pendiente superviviente~X equivalente con `ON CONFLICT DO NOTHING`, salvo que superviviente = X. Por el `CHECK (lead_a < lead_b)` se inserta como `lead_a = least(superviviente, X)`, `lead_b = greatest(superviviente, X)`, y hereda `busqueda_id` y `similitud` de la pendiente cerrada (H~X): la similitud es la de X contra el absorbido, que es la evidencia que existe; no se recalcula.
- `cumplimiento` no se toca: la fila del absorbido queda como registro de su origen.
- **Contrato para la 007:**
  - excluye los leads con `fusionado_en`, además de los que tienen revisión pendiente;
  - un `opt_out_at` en el `cumplimiento` de cualquier lead absorbido bloquea al superviviente. El opt-out se busca por la cadena `fusionado_en`, no solo por el `lead_id` del superviviente.
- Mientras una revisión está pendiente, los dos leads cuentan como únicos. El tablero muestra cuántas hay, porque inflan los únicos.

**Migración `supabase/migrations/0006_libro_costos_busqueda.sql`** (a mano, con `GRANT SELECT` de las vistas a `app_rt`):

| Objeto | Cambio |
|---|---|
| `busquedas` | `+ costo_estimado_usd numeric`, `+ costo_maximo_usd numeric`, `+ ejecutada_en`, `CHECK` de `estado` |
| `leads` | `+ fusionado_en uuid NULL`, `FOREIGN KEY (tenant_id, fusionado_en) REFERENCES leads (tenant_id, id)` (se apoya en `leads_tenant_id_id_key` de la 002; una FK simple no pasa por RLS: `test_rls.py::test_tenant_b_no_fusiona_con_lead_de_a`) |
| `revision_dedup` | `+ motivo text NULL` |
| `usuarios` | nueva (`auth_user_id` PK sin FK, `tenant_id`, `idioma`), con RLS (arriba) |
| `tenant_de_usuario(uuid)` | función `SECURITY DEFINER` (arriba), devuelve también los dos idiomas |
| `fijar_idioma(uuid, text)` | función `SECURITY DEFINER` (arriba) |
| `costos` | índice `(tenant_id, lote_id)` |
| `lead_fuentes` | índice `(busqueda_id, fuente)` |
| vistas | las 9 de arriba, `security_invoker` |

Los `ALTER DEFAULT PRIVILEGES … ON TABLES` del 002 ya cubren las vistas nuevas para `anon`/`authenticated`, y el test de privilegios lo confirma.

**Estructura del frontend** `frontend/src/`:
- **Una carpeta por feature**, con `{Componente.tsx, Componente.test.tsx, api.ts, tipos.ts}`:
  - `api.ts`: las llamadas de esa feature, siempre a través de `api/cliente.ts`;
  - `tipos.ts`: las formas de request y respuesta.

  | Feature | Componente | Ruta | Slice |
  |---|---|---|---|
  | `acceso/` | `Login` | `/login` | 005 |
  | `busqueda/` | `NuevaBusqueda` | `/busqueda/nueva` | 005 |
  | `tablero/` | `Tablero` | `/tablero` | 005, y lo extienden 006, 007 y 008 |
  | `dedup/` | `ColaRevision` | `/dedup` | 005 (tarea 10, recortable) |
  | `mensajes/` | `Mensajes` | | 007 |
  | `respuestas/` | `Respuestas` | | 007 |
  | `privacidad/` | `Privacidad` | | 007 |
  | `calificacion/` | `Calificacion` | | 008 |

  `acceso/` y `dedup/` no salen de los tests de 005–008: son las pantallas `/login` y `/dedup` de este slice, y sin carpeta quedarían fuera de la regla.
- **`api/cliente.ts`:** el cliente HTTP, único, con `VITE_API_URL`. Un 401 borra el token y hace `window.location.assign('/login')`. No importa el router ni `acceso/`: así `api/` no depende de nada de `src/`.
- **`compartido/`:** solo lo que usan **dos o más** features. Algo que usa una sola vive en su feature. Los campos del formulario se quedan en `busqueda/` hasta que la 010 los prellene; ahí se mueven a `compartido/` en el mismo PR.
- **`test/`:** setup de Vitest (`setup.ts`, Testing Library + jest-dom) y de MSW (`servidor.ts`, sin handlers). Cada test declara sus handlers con `server.use(...)`, así que `test/` no importa ninguna feature.
- **`main.tsx` y `App.tsx`:** son la raíz de composición (el router). Es el único lugar que importa todas las features.

**Regla de límites:** una feature no importa de otra feature; solo de `compartido/` y `api/`.
- `compartido/` importa solo de `compartido/` y `api/`.
- `api/` no importa nada de `src/`.
- Los `*.test.{ts,tsx}` además pueden importar `test/`. Es un bloque de la flat config con `files` propio, y el código de producción no puede.
- No hay lógica de negocio en el cliente: el front formatea y no calcula (ver Vistas).
- El chequeo:
  - `eslint-plugin-boundaries`, con la regla `boundaries/element-types` en `default: 'disallow'`;
  - los tipos de elemento, **en este orden**, porque boundaries se queda con el primer patrón que matchea:

    | Tipo | Patrón | Puede importar |
    |---|---|---|
    | `app` | `src/main.tsx`, `src/App.tsx` (`mode: 'file'`) | todas las features, `compartido`, `api` |
    | `api` | `src/api` | nada |
    | `i18n` | `src/i18n` | nada |
    | `compartido` | `src/compartido` | `compartido`, `api`, `i18n` |
    | `test` | `src/test` | `compartido`, `api`, `i18n` |
    | `feature` | `src/*`, capturando el nombre | la misma feature, `compartido`, `api`, `i18n` |

    Nadie importa `app`. Sin el tipo `app` primero, `src/App.tsx` caería en `feature` como una feature llamada `App.tsx`. Lo mismo con `i18n`: sin su tipo, `src/i18n` sería una feature y toda feature que traduce violaría la regla. `app` también importa `i18n`.
  - corre con `eslint-import-resolver-typescript`, porque boundaries **ignora en silencio** los imports que no resuelve, y un `.tsx` sin resolver dejaría el canario verde por la razón equivocada. `import/no-unresolved` en `error` convierte ese silencio en error.
  - Si el 001 no dejó ESLint instalado, entran como devDependencies `eslint`, `typescript-eslint`, `eslint-plugin-boundaries`, `eslint-plugin-import` y el resolver.
  - La regla se sigue en el mismo sentido que el `layers` de import-linter en el back (002).
- `vitest.config.ts` incluye `src/**` y `tests/**`, y excluye `e2e/`, para que Vitest no levante los specs de Playwright.

**Idiomas** (es y en desde el primer componente):
- **`react-i18next`** + `i18next` (dependencias nuevas). `src/i18n/index.ts` inicializa con `resources` de `src/i18n/es.json` y `en.json`, importados estáticamente: sin backend HTTP ni carga perezosa, son dos archivos chicos. `fallbackLng: 'es'`.
- **Idioma de la UI:** el primero que exista de:
  1. `usuarios.idioma`, la elección explícita (`idioma_usuario` de `GET /usuarios/me`);
  2. `navigator.languages` cortado al código base (`en-US` → `en`), el primero que esté en `{es, en}`;
  3. `tenants.idioma` (`idioma_tenant` de `GET /usuarios/me`);
  4. `es`.

  En la pantalla de login todavía no hay usuario ni tenant: valen 2 y 4. La elige `elegirIdioma(languages, idiomaUsuario, idiomaTenant)` en `src/i18n/elegirIdioma.ts`, pura.
- **Selector** (`compartido/SelectorIdioma.tsx`, lo usan `acceso/` y el layout): llama a `i18n.changeLanguage` y, si hay sesión, a `PATCH /usuarios/me {idioma}`, y actualiza `idioma_usuario` en `sessionStorage`. En la pantalla de login solo cambia la pestaña: no hay usuario a quien guardárselo. `# ponytail:` si el `PATCH` falla, la UI queda en el idioma elegido y el próximo login vuelve al guardado; sin reintento ni aviso.
- **La API devuelve códigos, no texto:** motivos (`sin_mapeo_actividad`), estados y errores de validación (el nombre de la regla, no `msg`). El front traduce con `t('motivos.' + codigo)`. Un código sin clave se ve como la clave cruda, nunca como un hueco: el test de paridad atrapa la falta en un idioma, y la falta en los dos se ve en pantalla.
- **Fechas y montos:** `Intl.DateTimeFormat(i18n.language)` y `Intl.NumberFormat(i18n.language, {style: 'currency', currency: 'USD'})`, en una función de `compartido/formato.ts`. Sin librería de fechas.
- **Catálogo de actividades:** es el `config/actividades.yaml` del 003, que ya mapea CIIU → OSM; no se crea otra tabla. Cada entrada suma `nombre_es` (CIIU Rev. 4 A.C., DANE; reemplaza a `descripcion`) y `nombre_en` (ISIC Rev. 4, ONU), que puede faltar. `GET /actividades` devuelve `codigo`, `nombre_es` y `nombre_en` (o `null`): es dato de catálogo, no texto de la API. El front muestra el del idioma activo y, si falta, cae a `nombre_es`.
- **Literales en JSX:** `eslint-plugin-i18next` (devDependency nueva), regla `i18next/no-literal-string` en `error` con `mode: 'jsx-only'`, sobre `src/**/*.tsx` menos `*.test.tsx`. `jsx-only` deja pasar las rutas y las claves de objetos, que no son texto visible.
- **El idioma del mensaje al lead no sale de acá:** lo fija `leads.idioma_contacto` por país (002) y lo usa el 007.

**Variables de entorno nuevas:**
- `AUTH_JWKS_URL`, `AUTH_ISSUER` y `WEB_ORIGIN` (api);
- `VITE_SUPABASE_URL` y `VITE_SUPABASE_PUBLISHABLE_KEY` (web; la publishable key es pública por diseño, y necesita la enmienda de constitución:30);
- `CROMA_BASE_URL` (override de la base de Croma, igual que `OVERPASS_URL`; los dos solo se usan en CI y en el E2E).

## Plan de tareas (TDD, en orden)
1. **Migración `0004` + vistas:**
   - `test_vistas_costos.py` con el fixture en rojo → verde. El **advisor revisa el fixture y los números calculados a mano antes de aceptarlos.**
   - Después, `test_rls[vista]`, `test_toda_vista_es_security_invoker` y `pg_views` en privilegios, en rojo → verde.
2. **`gasto_busqueda`** y lote = búsqueda: `test_costos_repo.py`, rojo → verde.
3. **`contar()`:** contrato rojo → Croma (con el test de una sola request) → Overpass.
4. **Selección y post-filtro:** 4a tamaño como refinamiento; 4b palabras clave y exclusiones.
5. **`VistaPrevia` + `EjecutarBusqueda` con tope** (unit). El **advisor revisa los tests de tope y de estimado.**
6. **Auth (Supabase Auth):** `usuarios`, `tenant_de_usuario`, verificador JWKS, `tenant_actual`, `GET /usuarios/me` y `PATCH /usuarios/me` con `fijar_idioma`. El **`security` revisa los tests de auth antes de aceptarlos.**
7. **Endpoints + validación:** `test_api_busquedas.py`.
8. **Front:**
   - Primero `limites.test.ts` en rojo: sin la config de boundaries, los tres negativos no dan error y `import_sin_resolver_es_error` tampoco. El control positivo y `el_repo_no_tiene_violaciones` nacerían verdes: se aceptan solo porque el canario crea los destinos y el escaneo exige los `results` conocidos (sin `App.tsx` todavía, el escaneo está en rojo). Después `eslint.config.js` → verde (≈ 25 min).
   - Después `i18n.test.ts` y `elegirIdioma.test.ts` en rojo: sin `es.json`/`en.json` falla la paridad, sin la regla `i18next/no-literal-string` fallan los canarios, y sin `elegirIdioma.ts` falla la precedencia. El control positivo nacería verde y se acepta solo porque el canario negativo está en rojo. Después `src/i18n/` y la regla → verde (≈ 20 min).
   - Después login, formulario y tablero, con Vitest en rojo → verde, ya dentro de la estructura por feature y con todo texto visible en `es.json`/`en.json`.
9. **E2E local** con el stub de fuentes en CI.
10. **Cola de revisión** (back + pantalla). **Es lo primero que se recorta:** sin ella, la cola se sigue resolviendo por SQL como en el 003.
11. **Una corrida real:** vista previa + Buscar contra Croma, avisada antes. Se anota el saldo antes y después para confirmar que fue 1 request y 1 crédito, si `total` viene en la respuesta real, y cuánto tarda la ejecución (el umbral de 30 s).
12. **`docs/arquitectura-backend.md` y `-frontend.md`:** vistas, lote = búsqueda, auth y cómo se agrega una columna al tablero. En `-frontend.md`, también la estructura por feature, la regla de límites y cuándo algo pasa a `compartido/`. También la corrección de PRD §4.

**Orden de corte**, si no alcanza el tiempo:
1. **10, la cola de revisión:** pasa al primer hueco libre del domingo (ya no al de la 011, que se construye el sábado antes de esta spec). Mientras tanto se resuelve por SQL, como en el 003.
2. **9, el E2E:** queda pendiente y la 013 lo lista en "qué es real y qué es simulado". La 012 no lo absorbe (es seguridad, no búsqueda).
3. **4b, palabras clave y exclusiones:** pasa a la 010. El formulario no muestra esos campos.
4. **`v_costo_por_canal`:** pasa a la 007. La 0004 queda con 8 vistas y `test_costo_por_canal` se va con ella.
5. **Cobertura por país y revisiones pendientes en el tablero:** quedan pendientes y la 013 las lista en "qué es real y qué es simulado".

**Mínimo para la demo:** 1, 2, 3, 4a, 5, 6, 7 y 8, con el tablero mostrando solo encontrados, únicos, ICP, costo lista y real, desperdicio, CPL, costo de evals y atribución. PRD §9 pone 003, 004 y 005 juntos el sábado a la tarde. Si la 003 o la 004 se pasan, la 005 arranca con el mínimo y el resto entra por el orden de corte.

## Riesgos
- **`total` de Supersociedades no verificado.** Si la respuesta real no lo trae, `contar` de cs devuelve `None` con `motivo='sin_conteo'`, y la vista previa muestra el resto. Se ve en el paso 11.
- **El truco de una sola request depende de que la clave de caché sea idéntica** entre `contar` y `buscar`. Lo cubre `test_contar_y_buscar_hacen_una_sola_request`; si alguien cambia los params de uno, el test falla.
- **El estimado de OSM es una cota baja.** Se declara en la pantalla, y el tablero muestra estimado contra real. Es un monto despreciable (USD 0.000007/s), pero se mide igual.
- **El CPL histórico cambia al fusionar.** Es el número correcto, porque refleja los leads reales, y queda probado en `test_lead_fusionado_no_cuenta`.
- **Una revisión pendiente infla los únicos.** Se muestra el conteo de pendientes al lado.
- **Request síncrona larga:** Overpass (timeout de cliente 30 s + reintento) + Croma (10 s + reintento) pueden pasar los 30 s. Se mide en el paso 11 y hay salida prevista (background con polling).
- **Token en el navegador y XSS:** `supabase-js` guarda la sesión en el almacenamiento del navegador. Mitigado por React y por no renderizar HTML de datos. Lo cierra la CSP de la 012.
- **El slice no entra completo en ≤ 5 h.** El mínimo para la demo está declarado, y cada recorte dice a qué slice va.
- **Dependencia de Supabase Auth y de su JWKS:** si Supabase cae, nadie entra; el JWKS se cachea. La api falla cerrado. El proyecto tiene que tener claves asimétricas (P17).
