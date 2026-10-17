# Spec 002 — Puertos, registro de adaptadores y Supersociedades

**Slice:** 002 · **Rama:** `feature/002-puertos-registro-supersociedades` · **Tiempo:** sábado AM/PM (≤ 4 h)
**Depende de:** 001. **Desbloquea:** 003, 004, 005, 006 (todo lo que consume `leads`).

> Las ramas son `feature/NNN-…` por decisión del dueño, igual que el 001. `slice-tdd` todavía dice `slice/` y se alinea en el PR de este slice.

## Para quién
- **El equipo:** el patrón puerto + registro + suite de contrato queda puesto, y todos los adaptadores siguientes lo copian.
- **La pyme usuaria (o Dapta operando por ella):** con un ICP de prueba (CIIU + departamento) obtiene empresas colombianas reales, cada una con su fuente, su costo y su fila de cumplimiento. En este slice se usa por CLI; la pantalla llega en 005.

## Qué hace
El primer módulo de negocio, `descubrimiento`, trae cuatro piezas:
- el puerto `FuenteDescubrimiento`;
- la carga de `config/fuentes.yaml`, que decide qué adaptadores existen;
- la suite de contrato, parametrizada sobre el registro;
- el primer adaptador real, `croma_supersociedades_co`.

Una búsqueda (ICP = país + CIIU + departamento) produce filas en `leads`, `lead_fuentes` y `cumplimiento`, deduplicadas por `(pais, NIT)` y con `tipo_titular=juridica`. Cada request HTTP a Croma escribe su fila en `costos` antes de devolver.

## Puertos y adaptadores que toca (`config/fuentes.yaml`)
- **`fuentes_descubrimiento.croma_supersociedades_co`** (`habilitado: true`): implementa `FuenteDescubrimiento`. En este slice usa los filtros `ciiu` y `departamento`.
- **`limites.croma_requests_por_24h`** (100): si se agota, el adaptador se niega a llamar.
- **`limites.croma_creditos_gratis_mes`** (1.500): si se agota, el adaptador sigue llamando pero registra `gratis=false`. El tope de gasto real lo pone el 005.
- **`RegistroCostos` ← `postgres_costos`** (PRD §3): en este slice solo se escriben filas. Las fórmulas, el prorrateo y el tablero son del 005.
- **Sección `fuentes_descubrimiento` del registro:** es la única que este slice carga y valida.
  - Las claves con `habilitado: true` que todavía no tienen implementación (`croma_dian_trade_co`, `osm_overpass`) se reportan como `sin_implementacion`; no rompen la carga.
  - `enriquecedores`, `canales_contacto`, `calificadores` y `clasificadores` se cargan en los slices de su puerto (006, 007, 008).

## Skills que aplican
- `fuentes-publicas`: puerto, normalización a `EmpresaCruda`, paso 1 del dedup, límites de Croma, no redistribuir.
- `libro-costos`: `OperacionCosto` de tipo `croma_consulta` y el campo `gratis`.
- `cumplimiento-datos`: `tipo_titular` y fila en `cumplimiento`.
- `slice-tdd`.

## Evals
Ninguno: este slice no usa IA. Las empresas que encuentra alimentan `backend/evals/dataset.json` en el 004.

## Flujo principal
1. `uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11` crea una fila en `busquedas` con el ICP.
2. El orquestador lee el registro y toma los adaptadores habilitados e implementados cuyos `paises` y `filtros` cubren el ICP. A cada uno le llama `buscar(criterios, pagina)`. Si ninguno cubre el ICP, devuelve `sin_fuente_para(pais, criterio)`.
3. El adaptador consulta `fuente_cache`:
   - **Hay hit:** no gasta crédito.
   - **No hay hit y queda límite:** hace `POST /co/supersociedades/companies-search/v1` con `per_page=100`. Escribe una fila en `costos` por cada intento HTTP enviado, reintentos incluidos, y guarda la respuesta cruda en el caché.
   - En ambos casos devuelve `EmpresaCruda` normalizada, con el NIT en solo dígitos (sin puntos ni DV).
4. `EjecutarBusqueda` deduplica por `(pais, id_fiscal)`:
   - **Lead nuevo:** se inserta con `tipo_titular` y se crea su fila en `cumplimiento` (fuente, licencia, `url_origen`, `as_of`, base legal pendiente).
   - **Lead existente:** se reutiliza y no se toca `cumplimiento`.
   - En los dos casos se agrega una fila en `lead_fuentes` por `(lead, fuente, búsqueda)`.
5. La CLI imprime el resumen: encontrados · únicos · nuevos · créditos gastados · fuentes sin implementación.

## Terminado cuando (tests que hoy fallan)

**Arquitectura y registro**
- `backend/tests/arquitectura/test_import_linter.py::test_detecta_violacion_de_capas`: un canario en `tmp_path` donde `descubrimiento/dominio` importa `descubrimiento/infraestructura` hace que `lint-imports` salga con código ≠ 0 y nombre el contrato `layers`. Sobre el repo real sale con 0.
- `backend/tests/arquitectura/test_import_linter.py::test_descubrimiento_no_importa_costos_infraestructura`: un canario donde un módulo de `descubrimiento` importa `app.modulos.costos.infraestructura` hace que `lint-imports` salga con código ≠ 0 y nombre el contrato `forbidden`.
- `backend/tests/unit/descubrimiento/test_dominio.py`:
  - `::test_normalizar_nit[…]`: `"900.123.456-7"` → `"900123456"`; `"900123456"` → `"900123456"`; `"9001234567"` → `"9001234567"` (sin guion no se corta el DV).
  - `::test_cubre[…]`: `cubre(meta, criterios)` es verdadero por país y por `"*"`, y falso con un filtro fuera de `meta.filtros`.
- `backend/tests/unit/descubrimiento/test_registro.py`:
  - `::test_carga_config_fuentes_yaml_real_sin_error`: carga el `config/fuentes.yaml` del repo, devuelve `croma_supersociedades_co` y deja `sin_implementacion == {"croma_dian_trade_co", "osm_overpass"}`.
  - `::test_solo_carga_adaptadores_habilitados`: con un YAML de prueba que tiene un adaptador `true` y uno `false`, devuelve solo el primero.
  - `::test_habilitado_sin_implementacion_se_reporta`: la clave aparece en `sin_implementacion` y la carga no lanza.
  - `::test_fuente_habilitada_sin_paises_o_filtros_falla`: una entrada de `fuentes_descubrimiento` con `habilitado: true` y sin `paises` o sin `filtros` lanza `RegistroInvalido`.
  - `::test_deshabilitada_incompleta_no_se_valida`: una entrada `habilitado: false` sin `paises` ni `filtros` no lanza.
  - `::test_clave_del_catalogo_ausente_del_yaml_falla`: una clave del catálogo que no está en el YAML lanza `RegistroInvalido`.
- `backend/tests/arquitectura/test_registro_adaptadores.py::test_todo_adaptador_de_registro_esta_declarado`: toda clase en `infraestructura/adaptadores/` que implementa un puerto del registro (`FuenteDescubrimiento`, `Enriquecedor`, `CanalContacto`, `Calificador`, `Clasificador`) está en el catálogo, y su clave existe en `config/fuentes.yaml`.
  - **Exclusión:** una lista cerrada, `EXCLUIDOS = {costos/infraestructura/postgres_costos.py, descubrimiento/infraestructura/persistencia/repositorio_leads.py, descubrimiento/infraestructura/persistencia/repositorio_cache.py}`. Razón: son repositorios de la DB propia, y no hay registro que los conecte o desconecte.
  - `::test_persistencia_solo_contiene_excluidos_y_no_importa_http`: falla si en `persistencia/` aparece un archivo fuera de `EXCLUIDOS`, o si alguno importa `httpx`, `requests` o `urllib`. Así un cliente HTTP no puede esconderse ahí.
- `backend/tests/arquitectura/test_costos_por_adaptador.py::test_todo_adaptador_de_registro_recibe_registro_costos`: toda clase de `infraestructura/adaptadores/` que implementa un puerto del registro, con el mismo criterio del test anterior, tiene `RegistroCostos` en su constructor. Las excepciones y los helpers quedan fuera.
  - **Exclusión:** la misma lista `EXCLUIDOS`. Razón: el I/O externo es la red, no la base propia, y `postgres_costos` es el registro mismo.

**Contrato del puerto** (`backend/tests/contratos/test_fuente_descubrimiento.py`, parametrizado sobre el catálogo, con transporte falso)
- `::test_hay_fabrica_para_cada_clave_del_catalogo`: toda clave del catálogo tiene fábrica en `fabricas.py`, y `assert catalogo` a nivel de módulo impide que un catálogo vacío deje la suite verde sin correr.
- `::test_devuelve_empresas_normalizadas[croma_supersociedades_co]`: cada empresa trae `pais`, `nombre`, `fuente`, `url_origen`, `as_of` y `actividad` con su `sistema`.
- `::test_registra_costo_antes_de_devolver[…]`: hay una fila por intento HTTP en el `RegistroCostos` falso, escrita antes de que `buscar` retorne.
- `::test_rechaza_criterio_no_soportado[…]`: la clave centinela `"__criterio_inexistente__"`, que ninguna fuente soporta (no una clave real), lanza `CriterioNoSoportado` y no se hace ningún request.

**Adaptador Croma** (`backend/tests/unit/descubrimiento/test_croma_supersociedades.py`, con fixture JSON **sintética**: Croma no se redistribuye)
- `::test_mapea_respuesta_a_empresa_cruda`:
  - `900.123.456-7` queda como `id_fiscal == "900123456"`;
  - `tipo_titular == "juridica"`;
  - `actividad == ("4711", "CIIU")`;
  - ciudad y dirección presentes.
- `::test_registra_un_credito_por_request`: la fila tiene `tipo="croma_consulta"`, `unidades=1`, `costo_unitario == tarifas.croma.usd_por_credito`, `proveedor="croma"`, `fuente="croma_supersociedades_co"`, `lead_id=None` y el `lote_id` de la corrida.
Los contadores son del puerto: `RegistroCostos.requests_24h(proveedor)` y `RegistroCostos.creditos_mes(proveedor)`. Acá el falso devuelve números fijos y se prueba la decisión del adaptador. El SQL de los contadores se prueba en integración.
- `::test_dentro_del_cupo_mensual_registra_gratis`: con `creditos_mes=1499`, la fila sale con `gratis=True`.
- `::test_cupo_mensual_agotado_registra_no_gratis`: con `creditos_mes=1500`, la fila sale con `gratis=False` y el mismo `costo_unitario`.
- `::test_no_llama_si_se_agoto_el_limite_de_24h`: con `requests_24h=100` y `creditos_mes=0`, lanza `LimiteFuenteAgotado` y el transporte recibe 0 requests.
- `::test_limite_de_24h_usa_requests_no_creditos`: con `requests_24h=99` y `creditos_mes=990`, no lanza y se hace la request.
- `::test_reintento_tras_502_registra_cada_intento`: un 502 seguido de un 200 da 2 requests y 2 filas en el registro falso. La del 502 lleva `unidades=0` y `costo_unitario=0`; la del 200, `unidades=1`. El gasto suma 1 crédito y la búsqueda devuelve las empresas.
- `::test_respuesta_cacheada_no_gasta_credito`: la primera búsqueda llena el caché vía el adaptador; la segunda idéntica hace 0 requests y escribe 0 filas nuevas.
- `::test_body_enviado_a_croma`: el body trae `ciiu_code`, `department` (desde `departamento`), `per_page=100` y `page=1`; la API key no está en el body ni en el hash del caché.
- `::test_502_con_99_previas_no_reintenta`: con 99 requests previas, un 502 da 1 request, 1 fila escrita y `LimiteFuenteAgotado`.
- `::test_429_lanza_limite_sin_reintento`: 1 request, 1 fila con `unidades=0` y `LimiteFuenteAgotado`.
- `::test_error_no_se_cachea`: tras un 4xx o un 5xx agotado el caché sigue vacío y la siguiente búsqueda sí hace request.

**Caso de uso** (`backend/tests/unit/descubrimiento/test_ejecutar_busqueda.py`, con repositorio falso)
- `::test_mismo_nit_de_dos_fuentes_queda_en_un_lead`: dos `EmpresaCruda` `(CO, 900123456)` de **fuentes distintas** dan 1 lead con 2 `lead_fuentes`.
- `::test_misma_fuente_repetida_no_duplica_lead_fuentes`: la misma empresa dos veces, de la misma fuente y en la misma búsqueda, da 1 lead con 1 `lead_fuentes`.
- `::test_nit_con_y_sin_formato_es_el_mismo_lead`: `900.123.456-7` y `900123456` dan 1 lead.
- `::test_mismo_nit_distinto_pais_son_dos_leads`.
- `::test_lead_existente_en_segunda_busqueda_no_duplica_cumplimiento`: dos búsquedas con el mismo NIT dan 1 lead, 1 `cumplimiento` y 2 `lead_fuentes` (una por `busqueda_id`).
- `::test_cada_lead_nuevo_tiene_fila_en_cumplimiento`: con fuente, licencia y `as_of`.
- `::test_sin_fuente_para_el_pais_se_reporta`: un ICP con `pais=BR`, teniendo solo Croma en el catálogo, devuelve `sin_fuente_para("BR", …)` y 0 leads.
- `::test_error_de_fuente_se_reporta_y_busqueda_queda_con_errores`: una fuente que lanza `LimiteFuenteAgotado` o `FuenteNoDisponible` aparece en el resultado con su error, sin tragarlo, y la búsqueda cierra `con_errores`.

**CLI** (`backend/tests/unit/test_cli.py`)
- `::test_buscar_sin_tenant_falla`: `buscar` sin `--tenant` sale con error.
- `::test_buscar_imprime_resumen`: con transporte falso inyectado, imprime el resumen.
- `::test_salida_no_contiene_secretos`: ni la API key ni la `DATABASE_URL` aparecen en stdout o stderr.
- `::test_tarifa_croma_es_decimal_exacto`: la tarifa que el CLI le pasa al adaptador es exactamente `Decimal("0.00099")`. Rojo si se carga como `float`.

**Integración** (Postgres de prueba, rol `app_rt`)
- `backend/tests/integration/test_leads_repo.py`:
  - `::test_unico_por_tenant_pais_id_fiscal`: un segundo INSERT con el mismo `(tenant_id, pais, id_fiscal)` viola la restricción.
  - `::test_unico_lead_fuente_busqueda`: un segundo INSERT en `lead_fuentes` con el mismo `(lead_id, fuente, busqueda_id)` viola la restricción, y `EjecutarBusqueda` lo resuelve con `ON CONFLICT DO NOTHING`.
  - `::test_lead_persistido_conserva_tipo_titular`: una `EmpresaCruda` de Supersociedades, guardada y releída, tiene `tipo_titular == 'juridica'`.
  - `::test_lead_nuevo_y_cumplimiento_en_una_transaccion`: si falla el INSERT del `cumplimiento`, no queda ninguna fila en `leads`.
  - `::test_crear_busqueda_se_confirma_antes`: la fila de `busquedas` es visible desde otra conexión antes de que se llame a ningún adaptador.
- `backend/tests/integration/test_costos_repo.py::test_croma_consulta_escribe_fila_en_costos`: el adaptador, con transporte falso y `postgres_costos` real, deja en `costos` 1 fila con `tipo='croma_consulta'`, `unidades=1`, `costo_unitario=0.00099`, `gratis=true` y el `tenant_id` del contexto. Es el chequeo del principio VIII.
- Contadores contra Postgres real, también en `test_costos_repo.py`. Siembran relativo a `now()` de la DB y usan `unidades` 0, 1 y 10:
  - `::test_requests_24h_cuenta_filas_en_ventana`: una fila a 23 h 59 min y otra a 24 h 01 min dan `requests_24h == 1`, aunque la fila de adentro tenga `unidades=0`.
  - `::test_creditos_mes_suma_unidades_del_mes_calendario_utc`: filas de 10 créditos a las 23:59 UTC del último día del mes anterior, y filas de 1 y 10 a las 00:01 UTC del primero del actual. Solo suman las del mes actual. El test corre con `SET TIME ZONE 'America/Bogota'` para probar que se usa UTC y no la zona de la sesión.
  - `::test_reintento_cuenta_para_el_limite`: con 98 filas previas de `unidades=1`, un 502 (fila con `unidades=0`) seguido de un 200 (fila con `unidades=1`) deja 100 filas: `requests_24h == 100` y `creditos_mes` pasa de 98 a 99. La búsqueda siguiente lanza `LimiteFuenteAgotado`. Un `SUM(unidades)` en lugar de `COUNT(*)` daría 99 y no cortaría.
  - `::test_cache_misma_clave_pisa_respuesta`: guardar dos veces con la misma `(proveedor, endpoint, hash_params)` deja 1 fila con la segunda respuesta.
  - `::test_cache_lectura_devuelve_respuesta_y_as_of`.
  - `::test_registrar_sobrevive_al_rollback_de_otra_transaccion`: una fila registrada mientras otra transacción hace rollback queda en `costos`.
- `backend/tests/integration/test_rls.py::test_tenant_b_no_accede_a_datos_de_a[tabla]`, sobre `tenants`, `busquedas`, `leads`, `lead_fuentes`, `cumplimiento` y `costos`. En `tenants` la política es `id = app.tenant_id`, y `app_rt` no tiene `INSERT`: la siembra corre con `postgres`. Como tenant B:
  - SELECT devuelve vacío;
  - UPDATE y DELETE afectan 0 filas de A;
  - un INSERT con el `tenant_id` de A es rechazado.

  `fuente_cache` va en la lista de exclusiones, con su razón (ver Decisiones técnicas).
- `backend/tests/integration/test_rls.py::test_tenant_b_no_cuelga_filas_de_un_lead_de_a[tabla]`, sobre `lead_fuentes` y `cumplimiento`: como tenant B, un INSERT con su propio `tenant_id` y el `lead_id` de un lead de A falla con `ForeignKeyViolation`. La FK no pasa por RLS: solo la FK compuesta `(tenant_id, lead_id)` lo frena.
- `backend/tests/integration/test_privilegios_supabase.py` (los dos primeros corren con `postgres`, que puede leer el catálogo):
  - `::test_anon_y_authenticated_sin_privilegios[rol-tabla]`: para `anon` y `authenticated`, sobre cada tabla de `public` (`fuente_cache` incluida), `has_table_privilege(rol, tabla, priv)` es `false` para `SELECT`, `INSERT`, `UPDATE` y `DELETE`. La lista de tablas sale de `pg_tables WHERE schemaname='public'`, no de una lista fija: una tabla nueva entra sola. Un assert previo exige que la lista contenga al menos `leads`, para que una lista vacía no deje la suite verde sin correr nada.
  - `::test_default_privileges_no_conceden_a_anon_ni_authenticated`: después de aplicar `supabase/migrations`, `postgres` crea una tabla **regular** `public.x` dentro de una transacción con rollback, y `anon`/`authenticated` no tienen ningún privilegio sobre ella. No una `TEMP TABLE`: esa va a `pg_temp` y no le aplican los defaults de `public`.
  - `::test_tenant_no_sobrevive_al_commit`: usa la unidad de trabajo real sobre el engine de `app_rt`, no un `SET LOCAL` escrito en el test. Dentro de la unidad de trabajo, `current_setting('app.tenant_id', true)` es el tenant; después del commit, en la misma conexión, es vacío o `NULL`. Prueba que el código usa `SET LOCAL` y no `SET` de sesión.
  - Que `app_rt` no tiene `BYPASSRLS` ya lo prueba `test_rol_runtime` del 001.
- `backend/tests/arquitectura/test_migraciones.py::test_migrar_local_desde_vacio_dos_veces_sin_drift` (del 001): hoy afirma `_aplicadas(base_vacia) == "0001"`, así que la `0002` lo pone en rojo. Se cambia ese assert para comparar contra las versiones de `supabase/migrations/*.sql`, ordenadas y unidas por coma. Así ninguna migración siguiente lo vuelve a romper. Lo que prueba no cambia: desde vacío, dos corridas, sin drift y todas las migraciones registradas.
  - La ruta sale del mismo default que `migrar_local.sh` (`BACKEND.parent / "supabase" / "migrations"`, sin pasar `MIGRACIONES`); la versión es lo que va antes del primer `_`, y el orden es de texto, como el `ORDER BY version` de `_aplicadas`.
- `backend/tests/integration/test_sembrar_tenant.py`:
  - `::test_sembrar_dos_veces_mismo_id_actualiza`: con `postgres`, la segunda siembra del mismo `id` cambia `nombre` e `idioma` (`'es'` → `'en'`) y no falla. Queda 1 fila con ese `id`, con el `nombre` y el `idioma` nuevos. El test llama a la función de siembra con una conexión, no al prompt de `getpass`.
  - `::test_no_imprime_la_url_de_postgres`: `getpass` se reemplaza con monkeypatch por una URL con una password marcadora y host inalcanzable, y se corre el `main`. El exit code es distinto de 0 y la password no aparece ni en stdout ni en stderr (`capsys`).

## Fuera del alcance
- **003:** OSM, normalización entre fuentes, dedup por dominio, teléfono o nombre difuso, y DIAN Trade.
- **005:** fórmulas de CPL, prorrateo, costo de cómputo, tablero, formulario, endpoint HTTP de búsqueda, auth de usuarios (llega con el primer endpoint que gasta créditos) y tope de gasto en USD.
- **006:** carga de `enriquecedores`, `contactable` y cifrado del contacto. Este slice no agrega ninguna columna sensible: NIT, razón social y dirección de una persona jurídica no son datos personales.
- Paginación más allá de la página 1. El puerto ya trae el parámetro `pagina`.

## Decisiones técnicas

**Módulo** `backend/app/modulos/descubrimiento/`:
- `dominio/`: `EmpresaCruda`, `CriteriosICP` (`filtros: Mapping[str, str | tuple[str, ...]]`; la tupla son varios valores), `MetaFuente`, `PaginaEmpresas`, `normalizar_nit` y los Protocols `FuenteDescubrimiento` y `RepositorioLeads`.
- `aplicacion/`: `EjecutarBusqueda` y `cargar_registro`.
- `infraestructura/adaptadores/croma_supersociedades.py`.
- `infraestructura/persistencia/{repositorio_leads,repositorio_cache}.py`.

**Puerto:** `buscar(criterios, pagina)` devuelve `PaginaEmpresas(empresas, total)`, no una lista suelta de `EmpresaCruda`: el 005 necesita `total` para la vista previa. Decidido en el plan (pregunta abierta 15) y aprobado por el dueño.

**Módulo** `backend/app/modulos/costos/` (dueño del libro de costos; el 005 le suma fórmulas y tablero):
- `dominio/`: `OperacionCosto` y el Protocol `RegistroCostos`.
- `infraestructura/postgres_costos.py`.

**import-linter:** contrato `layers` (`infraestructura > aplicacion > dominio`) para `app.modulos.*`, con el canario. Paga la deuda que dejó el 001. Más un contrato `forbidden`: `app.modulos.descubrimiento` no importa `app.modulos.costos.infraestructura`; `app.cli` es la única raíz que los une.

**Registro:**
- `cargar_registro(ruta_yaml, catalogo)` lee solo `fuentes_descubrimiento`. Si el catálogo tiene una clave que no está en el YAML, lanza `RegistroInvalido`.
- `catalogo` es un dict `clave → clase` en `infraestructura/adaptadores/__init__.py`. Es el único lugar que conoce las clases concretas.
- El dominio recibe instancias ya construidas.
- `# ponytail:` una sección por slice. Cuando haya un segundo puerto cargado (006), el loader se generaliza por sección.

**Tablas** (migración `supabase/migrations/0002_descubrimiento.sql`, a mano, con `GRANT` a `app_rt` según la plantilla del 001):

| Tabla | Columnas | Restricciones |
|---|---|---|
| `tenants` | `id`, `nombre`, `idioma`, `creado_en` | Se siembra con el tenant del evento desde `backend/scripts/sembrar_tenant.py`. `idioma` NOT NULL DEFAULT `'es'`, CHECK `IN ('es','en')`: idioma de UI por defecto del tenant (lo usa el 005). |
| `busquedas` | `pais`, `criterios jsonb`, `creado_en`, `estado`, `canal_preferido`, `tope_gasto_usd`, `mensaje_base` | `creado_en timestamptz NOT NULL DEFAULT now()`: historial y CPL por período (005). |
| `leads` | `pais`, `id_fiscal`, `nombre`, `tipo_titular`, `ciudad`, `direccion`, `actividad_codigo`, `actividad_sistema`, `web`, `idioma_contacto`, `creado_en` | `creado_en timestamptz NOT NULL DEFAULT now()`. `id_fiscal` nullable (por OSM). `tipo_titular` ∈ `juridica`/`natural`/`desconocido`, NOT NULL, default `desconocido`. UNIQUE `(tenant_id, pais, id_fiscal)` y UNIQUE `(tenant_id, id)` (destino de las FK compuestas). `idioma_contacto` es `GENERATED ALWAYS AS (CASE pais WHEN 'CO' THEN 'es' WHEN 'MX' THEN 'es' WHEN 'PE' THEN 'es' WHEN 'BR' THEN 'pt' END) STORED`: el idioma del mensaje sale del país, nunca de la UI, y lo fija la base, no la app. `'pt'` es un dato, no una traducción: sin plantilla pt, el 007 lo marca `sin_plantilla_idioma`. Un país nuevo sin rama da `NULL`, que pasa a lo mismo. |
| `lead_fuentes` | `lead_id`, `busqueda_id`, `fuente`, `encontrado_en`, `url_origen`, `licencia` | UNIQUE `(lead_id, fuente, busqueda_id)`. FK compuesta `(tenant_id, lead_id) → leads (tenant_id, id)`: una FK no pasa por RLS, y con una simple un tenant que conozca el uuid de un lead ajeno le cuelga filas. |
| `cumplimiento` | `lead_id`, `fuente`, `licencia`, `url_origen`, `base_legal`, `as_of`, `opt_out_at`, `solicitudes jsonb` | `lead_id` UNIQUE. FK compuesta `(tenant_id, lead_id) → leads (tenant_id, id)`, por lo mismo. `base_legal` nullable hasta el 007 (la setea `AprobarMensaje`). |
| `costos` | las columnas de `OperacionCosto` + `gratis` | `gratis bool NOT NULL`. CHECK de `tipo` con la lista cerrada de la skill `libro-costos` (`overpass_query` incluido, para la 003; lista exacta en plan.md). |

Todas menos `tenants` llevan `tenant_id` y RLS con `USING/WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)`. `tenants` tiene RLS con `USING (id = current_setting('app.tenant_id')::uuid)`, solo `GRANT SELECT` a `app_rt`, y se siembra con `postgres`. La siembra la corre un humano desde local: `sembrar_tenant.py` pide la URL de `postgres` por `getpass`, nunca por argv, por `DATABASE_URL` ni por una variable en Railway (ahí `api` solo tiene `app_rt`). Hace upsert por `id` (`INSERT … ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, idioma = EXCLUDED.idioma`), con `--id` opcional: sin `--id` genera un uuid y lo imprime. Así se puede volver a correr sobre un tenant existente, y el 007 le suma `--firmante` y `--finalidad`. La unidad de trabajo abre la transacción y hace `SET LOCAL app.tenant_id` (o `set_config(..., true)`) como primera sentencia. **Nunca `SET` de sesión:** `api` entra por el pooler de Supabase en modo transacción, y una conexión con el tenant de otro cliente puede llegar a la request siguiente.

**Roles de Supabase** (en la misma `0002`, al final):
```sql
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
```
- La migración no puede fallar en Postgres vanilla: el bloque va dentro de un `DO` que solo corre si existen `anon` y `authenticated` (`pg_roles`).
- **CI y local:** `backend/scripts/supabase_simulado.sql` corre después de `roles.sql` y antes de aplicar `supabase/migrations`. Crea `anon` y `authenticated` `NOLOGIN` y simula el peor caso de Supabase: `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated`. Sin ese script, el test de privilegios nacería verde en vanilla y no probaría nada.

**`fuente_cache`** (`proveedor`, `endpoint`, `hash_params`, `respuesta jsonb`, `as_of`) es **global, sin `tenant_id`**:
- Guarda datos públicos de gobierno, no datos del tenant. Por eso queda excluida del test de RLS.
- Las respuestas cacheadas son de uso propio y no se exponen por API.

**Límites:**
- Los dos son métodos de `postgres_costos` (`requests_24h`, `creditos_mes`) y se cuentan desde `costos` (`proveedor='croma'`), sin tabla nueva. El adaptador solo decide con lo que le devuelven:
  - **Límite de 24 h:** `COUNT(*)` de las filas en `ts > now() - interval '24 hours'`. Cuenta requests.
  - **Cupo mensual:** `SUM(unidades)` dentro del mes calendario UTC (`ts >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'`; un `date_trunc` sobre `timestamptz` usaría la zona de la sesión). Cuenta créditos.
- Cada intento HTTP enviado escribe su fila, porque Croma limita por requests.
  - **Intento fallido** (5xx, timeout, 429 o cualquier otro 4xx): `unidades=0` y `costo_unitario=0`. Cuenta para el límite de 24 h, pero no infla el gasto ni el CPL.
  - Si Croma cobra los 5xx, se corrige en el paso 8.
- `# ponytail:` por RLS, la cuenta es por tenant. Con un solo tenant en el evento coincide con la cuenta de Croma; con varios tenants pasa a un contador global.

**HTTP:**
- `httpx`, con `MockTransport` en los tests.
- Timeout de 10 s y un reintento con backoff ante 502, 503 o timeout.
- `CROMA_API_KEY` viene del entorno vía el `config` de la app; el dominio nunca la ve.

**Tarifas:** `config/tarifas.yaml` se carga una vez, cada valor como `Decimal(str(v))` (nunca `float`), y el adaptador recibe el `costo_unitario` ya resuelto.

## Plan de tareas (TDD, en orden)
1. **Canario `layers`:** test en rojo → contrato en `pyproject.toml` → verde.
2. **Dominio + registro:** `EmpresaCruda`, `CriteriosICP`, `normalizar_nit`, los Protocols y `cargar_registro`. Los de `test_dominio.py` en rojo → verde. De los 4 de `test_registro.py`, el primero que se escribe es el del YAML real y **queda en rojo hasta T031**, cuando el catálogo registra `croma_supersociedades_co` (paso 5); los otros 3 pasan a verde en este paso.
3. **Migración `0002` + `persistencia/`:**
   - `supabase_simulado.sql` en CI primero, para que los tests de privilegios nazcan en rojo;
   - `test_unico_…`, `test_lead_persistido_conserva_tipo_titular`, `test_lead_nuevo_y_cumplimiento_en_una_transaccion`, `test_crear_busqueda_se_confirma_antes`, `test_rls[…]` y los 3 de `test_privilegios_supabase.py` en rojo → verde;
   - con la `0002` en el repo, `test_migrar_local_desde_vacio_dos_veces_sin_drift` queda en rojo por el `== "0001"`; se cambia el assert a las versiones de `supabase/migrations/*.sql` y vuelve a verde;
   - los 2 de `test_sembrar_tenant.py` en rojo → `sembrar_tenant.py` con upsert → verde;
   - el **advisor revisa los tests de RLS y de privilegios antes de aceptarlos**.
4. **`postgres_costos`:** contadores y `test_registrar_sobrevive_al_rollback_de_otra_transaccion` en rojo → verde. `test_todo_adaptador_de_registro_recibe_registro_costos` pasa al paso 6 (T036): antes del adaptador recorrería una lista vacía.
5. **Adaptador `croma_supersociedades_co`** con la fixture sintética:
   - mapeo, crédito, gratis/no gratis, 24 h, reintento y caché en rojo → verde;
   - después, `test_costos_repo.py`;
   - el **advisor revisa los tests de costos**.
6. **Suite de contrato** (con `test_hay_fabrica_para_cada_clave_del_catalogo`) + `test_todo_adaptador_de_registro_esta_declarado`, `test_persistencia_solo_contiene_excluidos_y_no_importa_http` y `test_todo_adaptador_de_registro_recibe_registro_costos`: rojo → verde.
7. **`EjecutarBusqueda`:** los 8 tests del caso de uso en rojo → verde. El **advisor revisa los tests de dedup**.
8. **CLI `app.cli buscar`:** los 4 de `test_cli.py` en rojo → verde. Después, **una** corrida real contra Croma: 1 request, avisada antes, anotando los créditos, la forma real de la respuesta y si Croma cobra los 5xx (lo dice su doc o el saldo antes y después). Si la forma difiere de la fixture, se corrige la fixture y se vuelve al paso 5.
9. **`docs/arquitectura-backend.md`:** módulo, puerto, registro y cómo agregar un adaptador. Si el tiempo aprieta, es lo primero que se recorta (queda en un párrafo).

## Riesgos
- **La forma real de la respuesta de Croma no está verificada.** La fixture sale de `docs.usecroma.com` y el paso 8 la contrasta con la respuesta real.
- **La cuota (100 req/24 h) se quema en desarrollo.** Los tests nunca tocan la red y el caché cubre las corridas manuales.
- **Croma devuelve 502 o tarda.** Hay un reintento, y queda registrado. Si también falla, el error se reporta en la búsqueda; no se traga.
- **Sesgo de Supersociedades:** solo trae medianas y grandes que reportan, así que con un ICP de micro-pymes rinde poco. Lo compensa OSM en el 003, y el sesgo se muestra en el tablero.
- **DV del NIT:** se guarda sin DV y `normalizar_nit` lo corta. Lo cubren el test de mapeo y el de dedup.
- **CI corre contra `postgres:16`, no contra Supabase.** `supabase_simulado.sql` emula `anon`/`authenticated` y sus default privileges, pero no `service_role` (que tiene `BYPASSRLS`) ni el resto del dashboard. Lo que la emulación no cubre se verifica a mano en producción tras el primer deploy: `has_table_privilege` desde `psql` y `curl /rest/v1/` sin `public` (quickstart del 001).
