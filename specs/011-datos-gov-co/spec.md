# Spec 011 — datos.gov.co (`c82u-588k`), segunda fuente de descubrimiento, con contrato

**Slice:** 011 · **Rama:** `feature/011-datos-gov-co` · **Tiempo:** sábado PM, justo después de la 003 (≤ 1,5 h con los cortes de "Cuándo cortar"; completo, ~2 h)
**Depende de:** 002 (puerto, registro, contrato, caché), 003 (normalización, dedup, selección de fuentes), 005 (`costo_maximo_llamada`, la suite de contrato de `contar` y el tablero, con sus tests movidos a specs/005 por D7). **Desbloquea:** el descubrimiento en CO sin depender del tier de Croma, la demo en vivo de que una fuente se conecta y se desconecta (PRD §9) y la atribución del README en la 013.

> **Orden 002 → 003 → 011.** **D7, resuelta por el dueño:** los 6 tests que dependen de la 005 se movieron a specs/005. Son `test_costo_maximo_llamada`, los tres de `contar` de la suite de contrato de la 005, `test_tablero_trae_naturales_por_fuente` y `muestra_naturales_encontradas_no_contactables`. En la 011 quedan solo `test_contar_usa_count_con_el_mismo_where` y `test_contar_registra_socrata_descarga`, que son rojo real por aserción: `contar` es un método del adaptador y no necesita nada de la 005. El PR de la 011 no lleva `xfail`.

> **Cambio de dataset.** El PRD §2 nombraba `nb3d-v3n7`. Al consultar la API real (2026-10-17) resultó ser "Establecimientos - Agencias - Sucursales": la identificación es la del **propietario** y **no distingue personas naturales**. En la verificación, 37 personas naturales tenían NIT de 9 dígitos con prefijo 8/9, y 24 de ellas tenían DV consistente, así que ninguna heurística sobre el NIT sirve. Esta spec usa **`c82u-588k`** ("Personas Naturales, Personas Jurídicas y ESAL", Confecámaras, CC BY-SA 4.0): es el registro mercantil, con una fila por matrícula y la naturaleza jurídica declarada en `organizacion_juridica`. Se mantiene el id de fuente `datos_gov_co_rues`. La nota quedó en el PRD §2.
>
> Rutas: `config/` es donde la deje el 001. Si ya entró `952738f`, es `backend/config/`.

## Para quién
- **El jurado y Dapta:** una segunda fuente pública y gratuita de descubrimiento en CO, junto a OSM, que no depende de los ~100 req/día de Croma y cubre las pymes pequeñas que no reportan a Supersociedades. Aporta volumen y cobertura, no contactabilidad: no trae teléfono ni web, y eso lo dan OSM y `sitio_web` (006). Además ven que se conecta y se desconecta con un flag en `config/fuentes.yaml`, sin tocar el dominio.
- **El equipo:** un tercer adaptador de `FuenteDescubrimiento` que pasa la misma suite de contrato y demuestra que el puerto aguanta una fuente con forma distinta: SODA, sin contacto y con la persona natural excluida en el servidor.

## Qué hace
- Un adaptador `datos_gov_co_rues` de `FuenteDescubrimiento` que consulta `c82u-588k` por CIIU y departamento. Filtra en el servidor `organizacion_juridica != 'PERSONA NATURAL' AND estado_matricula = 'ACTIVA'`, así que **las personas naturales nunca se descargan**.
- **Cuenta** las personas naturales con un `count(*)` aparte, que no trae filas. Ese número llega a la CLI y a `busquedas.naturales_por_fuente` como "encontradas, no contactables". La respuesta de ejecutar y el tablero lo muestran desde la 005 (D7).
- Lo declara en `config/fuentes.yaml` con **`habilitado: true`** desde que se implementa: entra a toda búsqueda CO junto a OSM y Croma. Con un YAML que lo pone en `false`, no se carga y no hace ni una request.
- Registra el costo `socrata_descarga` por intento. Cada lead nuevo lleva su fila en `cumplimiento` con `CC-BY-SA-4.0`.
- Tests sin red: una fixture bloquea toda conexión saliente que no sea a loopback.
- Aparece en la atribución del tablero ("Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)") en cuanto aporta un lead. La arma la 005 (`v_atribuciones`) por fuente presente, y esta spec no suma tests de atribución.

## Puertos y adaptadores que toca (`config/fuentes.yaml`)
- **`fuentes_descubrimiento.datos_gov_co_rues`** (`habilitado: true`, `paises: [CO]`, `licencia: CC-BY-SA-4.0`): implementa `FuenteDescubrimiento` (`buscar`, `contar`, `meta`) y entra al catálogo. Este slice le cambia cuatro cosas en el YAML:
  - `habilitado: false` → **`habilitado: true`**, en el mismo commit en que pasa la suite de contrato.
  - `dataset: nb3d-v3n7` → **`dataset: c82u-588k`**.
  - `filtros: [ciiu, camara, estado_matricula, tipo_propietario]` → **`filtros: [ciiu, departamento]`**. La cámara es una traducción interna del adaptador (ver Decisiones técnicas). El estado y la naturaleza jurídica los fija el adaptador: nadie los elige en el ICP.
  - `trae: [nit, nombre, ciiu, estado, tipo_titular]` → **`trae: [nit, nombre, ciiu, ciudad_camara]`**. `estado` siempre es "activa" y `tipo_titular` siempre es "juridica": los fija la consulta.
- **Resultado de página del puerto (002/003)**, el mismo objeto que hoy lleva `truncado` y `descartados_sin_nombre`, suma dos campos aditivos con default:
  - **`descartados_no_juridica: int = 0`**: filas que el cliente descartó por no ser jurídica válida (ver Decisiones técnicas). Croma y OSM no lo tocan y queda en `0`, que es verdad, porque no descartan por esa razón.
  - **`naturales_no_descargadas: int | None = None`**: naturales contadas y no descargadas.
- **`MetaFuente`** suma **`cuenta_naturales: bool = False`**. Solo `datos_gov_co_rues` lo declara `True`. Así quedan tres estados distintos:
  - con `cuenta_naturales=False` → "no aplica", y el campo siempre es `None`. Pasa con Croma y OSM: OSM trae `desconocido`, así que un `0` sería falso;
  - con `cuenta_naturales=True` y el campo en `None` → el conteo falló;
  - con `cuenta_naturales=True` y un `int` → el número contado.
- **`busquedas`:** columna nueva `naturales_por_fuente jsonb NOT NULL DEFAULT '{}'`, que solo guarda las fuentes con `cuenta_naturales=True` (`{fuente: int | null}`). La cubre la RLS que la tabla ya tiene.
- **`RegistroCostos` ← `postgres_costos`:** nuevo tipo de operación `socrata_descarga`. Ya está en la tabla de `libro-costos` y en el PRD:135.
- **`fuente_cache`** (de la 002): se reutiliza con `proveedor='datos.gov.co'`, sin cambios de esquema.
- **Archivo nuevo `config/camaras_co.yaml`:** las 58 cámaras de comercio con su código, nombre, municipio sede y departamentos DIVIPOLA. Es dato de dominio, como `actividades.yaml` en la 003.
- **Ningún otro adaptador cambia.**

## Skills que aplican
- `fuentes-publicas`: registro, `EmpresaCruda`, NIT en solo dígitos, contrato del puerto. Este slice **corrige la skill** (ver Plan, paso 1).
- `cumplimiento-datos`: solo personas jurídicas (regla 1), fila en `cumplimiento`, licencia CC BY-SA 4.0 con share-alike y atribución visible (regla 11). **Desvío declarado de la regla 4**, que dice que las naturales "se guardan… no se contactan". Acá ni se guardan: se cuentan. Guardar menos datos personales es el lado seguro, y el PRD:57 ("visibles en tablero, no contactadas") queda cumplido por el conteo. La skill se anota en el paso 1.
- `libro-costos`: `socrata_descarga` = segundos de cómputo × `computo_seg_usd`, con `proveedor='datos.gov.co'`.
- `slice-tdd`.

## Evals
Ninguno: este slice no usa IA.

## Flujo principal
1. **Conectado (estado del repo):** `cargar_registro` lee `habilitado: true` y lo carga. `uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11` lo consulta junto a OSM y Croma.
2. **Desconectado (demo):** `FUENTES_YAML=/ruta/a/fuentes-demo.yaml uv run python -m app.cli buscar …` con la misma búsqueda. El YAML de la demo es una copia del real con `datos_gov_co_rues.habilitado: false`: `seleccionar_fuentes` no lo ve y hace 0 requests a datos.gov.co.
3. `seleccionar_fuentes` (003, sin cambios) le pasa al adaptador `{ciiu: "4711", departamento: "11"}`. Lo que el adaptador no declara (`ciudad`, `ingresos_min`) queda en `ignorados`.
4. El adaptador, en `buscar(criterios, pagina=1)`:
   - valida el CIIU (`^\d{4}$`) y traduce el departamento a cámaras con `config/camaras_co.yaml` (11 → `{04}`; 25 → `{04, 14, 47, 58}`). Si algo no valida, lanza `CriterioNoSoportado` sin hacer requests;
   - **filas:** consulta `fuente_cache`. Si no hay hit, hace `GET /resource/c82u-588k.json` con el `$where` de jurídicas, `$limit=5000` y sin `$order` (ver Decisiones técnicas). Registra una fila `socrata_descarga` por intento, filtra en el cliente y guarda **las filas ya filtradas** en el caché;
   - **conteo de naturales:** consulta `fuente_cache` con su propia clave. Si no hay hit, hace `GET` con `$select=count(*)` y el `$where` de naturales. También registra el costo por intento y lo cachea;
   - mapea a `EmpresaCruda`, marca `truncado` si llegaron 5.000 filas y devuelve `naturales_no_descargadas`.
   - Con `pagina > 1` devuelve una página vacía sin hacer requests: hay una sola página (ver Decisiones técnicas).
5. `EjecutarBusqueda` (002/003) deduplica y persiste, igual que antes. Un NIT que ya existe por Supersociedades se fusiona por la regla 1, y `cumplimiento` no cambia. Un lead nuevo lleva su `cumplimiento` (`fuente='datos_gov_co_rues'`, `licencia='CC-BY-SA-4.0'`, `url_origen`, `as_of` del header) y su `lead_fuentes`. **El único cambio** es que guarda `{fuente: naturales_no_descargadas}` en `busquedas.naturales_por_fuente`, solo para las fuentes con `meta.cuenta_naturales=True`.
6. La CLI imprime el resumen por fuente de la 003, más `naturales (encontradas, no contactables)` y `descartados_no_juridica`. La respuesta de ejecutar de la 005 suma el mismo campo por fuente.
7. **Vista previa (005):** `contar` hace un `count(*)` con el mismo `$where` de jurídicas. Es exacto, porque hay una fila por NIT (ver Decisiones técnicas). Su costo es el de la 005 para fuentes de cómputo: los segundos medidos × `computo_seg_usd`.
8. **Tablero:** `GET /tablero/fuentes` suma `cuenta_naturales` (de `meta`) y `naturales_no_descargadas` por fuente, tomado de la última búsqueda completada del tenant que la consultó. Si la fuente no cuenta, el valor es "no aplica" y nunca `0`. *(Movido a specs/005 por D7.)*

## Terminado cuando (tests que hoy fallan)

**Registro y selección**
- `backend/tests/unit/descubrimiento/test_registro.py::test_carga_config_fuentes_yaml_real_sin_error`: **se invierte**: `datos_gov_co_rues` está en el catálogo, **se carga** (`habilitado: true`) y no aparece en `sin_implementacion`. Nace rojo: hoy el YAML real lo tiene en `false`. Su entrada del YAML real tiene `dataset == "c82u-588k"`, `filtros == ["ciiu", "departamento"]` y `licencia == "CC-BY-SA-4.0"`.
- `backend/tests/unit/descubrimiento/test_seleccion_fuentes.py::test_datos_gov_co_habilitada_recibe_ciiu_y_departamento`: con un registro en memoria que la habilita, el ICP CO/4711/11/Bogotá le pasa `{ciiu, departamento}`, y `ciudad` queda en sus `ignorados`. Nace rojo: con los `filtros` actuales la ignora por `sin_geografia`.
- `backend/tests/unit/test_cli.py::test_respeta_fuentes_yaml_del_entorno`: con `FUENTES_YAML` apuntando a un YAML temporal, la CLI carga ese registro y no `config/fuentes.yaml`; esa parte nace roja. La de "sin la variable, carga el del repo" es una guarda que nace verde, contra un default roto.

**Contrato del puerto** (`backend/tests/contratos/test_fuente_descubrimiento.py`)
- Los tres tests de la 002 corren también con `[datos_gov_co_rues]`, con transporte falso. La suite no se toca: lo único nuevo es que el adaptador entra al catálogo. Los tres de `contar` de la 005 con `[datos_gov_co_rues]` se movieron a specs/005 (D7).
- `::test_campos_aditivos_del_resultado`, nuevo y parametrizado sobre **todos** los adaptadores: `descartados_no_juridica` es un `int >= 0`. Si `meta.cuenta_naturales` es `False`, `naturales_no_descargadas is None`; si es `True`, vale `int >= 0` o `None`. Nace rojo porque los campos no existen. Croma y OSM lo pasan con los defaults (`0`, `None` y `cuenta_naturales=False`).
- `backend/tests/arquitectura/test_registro_adaptadores.py::test_todo_adaptador_de_registro_esta_declarado` y `test_costos_por_adaptador.py::test_todo_adaptador_de_registro_recibe_registro_costos` lo cubren sin tocarlos.

**Adaptador** (`backend/tests/unit/descubrimiento/test_datos_gov_co.py`, con fixtures **sintéticas** en `backend/tests/fixtures/datos_gov_co/`: `filas.json`, con el esquema real y NITs ficticios, y `conteo_naturales.json`, `[{"count": "26304"}]`)
- `::test_query_filtra_juridicas_en_servidor`: la request de filas lleva:
  - `$where` con `organizacion_juridica != 'PERSONA NATURAL'`, `organizacion_juridica IS NOT NULL`, `estado_matricula = 'ACTIVA'`, `cod_ciiu_act_econ_pri = '4711'`, `codigo_camara in('04')` y `nit IS NOT NULL`;
  - `$limit=5000`, **sin** `$order`, `$offset` ni `$group`.
- `::test_select_no_pide_columnas_de_personas`: `$select` es exactamente `nit,digito_verificacion,razon_social,cod_ciiu_act_econ_pri,codigo_camara,organizacion_juridica,fecha_renovacion`. No pide `numero_identificacion`, `primer_nombre`, `segundo_nombre`, `primer_apellido`, `segundo_apellido`, `representante_legal`, `num_identificacion_representante_legal` ni `clase_identificacion_rl`, y el test los enumera.
- `::test_conteo_de_naturales_sin_filas`: la segunda request lleva `$select=count(*)` y un `$where` con `organizacion_juridica = 'PERSONA NATURAL'` y los mismos filtros de estado, CIIU y cámara, sin `nit IS NOT NULL`. Con `conteo_naturales.json`, el resultado trae `naturales_no_descargadas == 26304`.
- `::test_conteo_de_naturales_falla_y_las_filas_siguen`: si el conteo da dos 503, `buscar` devuelve las empresas de todas formas, con `naturales_no_descargadas is None`. El costo de los dos intentos fallidos queda registrado.
- `::test_departamento_se_traduce_a_camaras`: 11 → `in('04')`; 25 → `in('04','14','47','58')`. Un departamento que no está en `camaras_co.yaml`, o un CIIU que no cumple `^\d{4}$` (`"47' OR '1'='1"`), lanza `CriterioNoSoportado` y el transporte recibe 0 requests.
- `::test_cliente_descarta_lo_que_no_debio_llegar`: la fixture trae, además de las empresas válidas, una fila de cada caso, y ninguna da `EmpresaCruda`:
  - (a) `organizacion_juridica == "PERSONA NATURAL"`;
  - (a') `organizacion_juridica == "Persona Natural "`: el cliente compara con `strip().upper()`;
  - (b) `nit` nulo;
  - (c) `nit` que no cumple `^[89]\d{8}$` (`"12345678"`);
  - (d) `razon_social` vacía.

  Resultado: `descartados_no_juridica == 5`. El servidor ya filtra (a) y (b); el test prueba que el cliente no confía en eso.
- `::test_descartados_no_se_loguean`: con `caplog` en `DEBUG` sobre todos los loggers (`httpx` incluido), ningún registro contiene el `nit` ni la `razon_social` de los casos (a), (a') y (b) a (d). **Es una guarda: nace verde** apenas el adaptador importa. Se comprueba poniendo a mano un `logger.debug(fila)` en el descarte y viendo que pasa a rojo.
- `::test_mapea_fila_a_empresa_cruda`:
  - `id_fiscal == nit`, `nombre == razon_social`, `pais == "CO"`;
  - `ciudad` = `municipio_sede` de la cámara (`"Bogotá"` para la 04);
  - `actividad == ("4711", "CIIU")`, `tipo_titular == "juridica"`, `licencia == "CC-BY-SA-4.0"`, `fuente == "datos_gov_co_rues"`;
  - `url_origen == "https://www.datos.gov.co/resource/c82u-588k.json?nit=900123456"`;
  - `direccion`, `telefono`, `email`, `web`, `geo`, `telefono_canal` y `email_canal` en `None`.
- `::test_as_of_sale_del_header`: `X-SODA2-Truth-Last-Modified: Fri, 02 Oct 2026 21:39:26 GMT` → `as_of == datetime(2026, 10, 2, 21, 39, 26, tzinfo=UTC)`. Sin el header, `as_of` es la hora de la consulta según el reloj inyectable.
- `::test_cinco_mil_filas_marca_truncado`: `truncado` se mide sobre las filas **crudas** que llegaron, antes del filtro del cliente. Con 5.000 filas, 3 de ellas descartables, `truncado is True`; con 4.999, `False`. En los dos casos, `total is None`: el total exacto lo da `contar`.
- `::test_pagina_2_vacia_sin_request`: `buscar(criterios, pagina=2)` devuelve 0 empresas y `truncado is False`, con 0 requests y 0 filas de costo.
- `::test_contar_usa_count_con_el_mismo_where`: `$select=count(*)` y el mismo `$where` de la request de filas. La respuesta `[{"count": "2015"}]` devuelve `2015`.
- `::test_contar_registra_socrata_descarga`: `contar` deja 1 fila `socrata_descarga` con los segundos medidos y el `lote_id` de la vista previa.
- `::test_registra_segundos_de_cada_intento`: en las filas, un 503 seguido de un 200, con el transporte falso avanzando el reloj 2 s y 3 s; después el conteo, que tarda 1 s. Resultado: 3 filas `tipo="socrata_descarga"` con `unidades` 2, 3 y 1, `costo_unitario == tarifas.computo_seg_usd` (un `Decimal`), `proveedor="datos.gov.co"`, `fuente="datos_gov_co_rues"`, `lead_id=None`, `gratis=False` y el `lote_id` de la corrida.
- `::test_segundo_fallo_lanza_fuente_no_disponible`: dos 503 (o dos timeouts) en las filas → `FuenteNoDisponible`, 2 filas de costo, ninguna request de conteo y un mensaje que no incluye el cuerpo de la respuesta.
- `::test_cache_hit_no_hace_request`: un segundo `buscar` con los mismos criterios da 0 requests y 0 filas nuevas de costo, con el mismo resultado, `naturales_no_descargadas` incluido.
- `::test_conteo_fallido_no_se_cachea`: si el conteo falló en el primer `buscar` (`None`), el segundo `buscar` sirve las filas desde el caché y reintenta solo el conteo. Hace 1 request en lugar de 0: está declarado.
- `::test_cache_no_guarda_lo_descartado`: después de un `buscar` con la fixture de los casos (a), (a') y (b) a (d), la `respuesta` de `fuente_cache` no contiene el `nit` ni la `razon_social` de ninguno de ellos.
- `::test_costo_maximo_llamada`: `meta.costo_maximo_llamada == 2 * 2 * 30 * computo_seg_usd`, porque son dos requests de dos intentos con 30 s de timeout cada uno. *(Movido a specs/005 por D7.)*
- `::test_app_token_va_en_header_y_nunca_en_logs`: con `DATOS_GOV_CO_APP_TOKEN=tok-falso-123`, las dos requests llevan `X-App-Token: tok-falso-123` y, con `caplog` en `DEBUG`, ningún registro contiene `tok-falso-123`, y tampoco lo contiene ningún `url_origen`. Sin la variable, no se manda el header. La parte del header nace roja. La de "nunca en logs" **es una guarda**: se comprueba con un `logger.debug(headers)` puesto a mano.
- `::test_url_se_puede_sobrescribir`: con `DATOS_GOV_CO_URL=http://stub.local`, la request va a ese host.

**Cámaras** (`backend/tests/unit/descubrimiento/test_camaras_co.py`)
- `::test_yaml_real_cubre_58_camaras_y_33_departamentos`: el `config/camaras_co.yaml` del repo carga, cada una de las 58 cámaras tiene al menos un departamento y cada uno de los 33 códigos DIVIPOLA (32 departamentos + Bogotá D.C.) tiene al menos una cámara.
- `::test_bogota_y_cundinamarca`: `camaras_de("11") == {"04"}` y `camaras_de("25") ⊇ {"04", "14", "47", "58"}`.

**Sin red** (`backend/tests/unit/test_sin_red.py`)
- `::test_conexion_saliente_falla`: dentro de `backend/tests/unit/` y `backend/tests/contratos/`, `socket.create_connection(("192.0.2.1", 443))` lanza `RedBloqueadaEnTests`. Lo garantiza una fixture `autouse` en los `conftest.py` de esas dos carpetas, que parchea `socket.socket.connect` y `connect_ex`. Nace rojo: hoy intenta conectar y falla por timeout o por red, no por la fixture.
- `::test_loopback_sigue_permitido`: una conexión a `127.0.0.1` no lanza `RedBloqueadaEnTests` (puede fallar por puerto cerrado, pero no por la fixture). **Nace verde a propósito:** es la guarda contra una fixture que bloquee todo y rompa los tests que usan loopback. Se escribe en el mismo paso que el anterior, y se comprueba que se pone en rojo si la fixture bloquea loopback.

**Integración** (Postgres de prueba, rol `app_rt`, transportes falsos)
- `backend/tests/integration/test_conectar_desconectar.py`:
  - `::test_yaml_real_consulta_datos_gov_co` (antes `test_yaml_real_no_toca_datos_gov_co`, **se invierte**): con el `config/fuentes.yaml` del repo y la red mockeada (transporte falso para datos.gov.co, OSM y Croma), `EjecutarBusqueda` CO/4711/11 hace al menos 1 request al transporte de datos.gov.co.
  - `::test_deshabilitada_por_yaml_temporal_no_toca_datos_gov_co`: el par del anterior. Con una copia del YAML real con `datos_gov_co_rues.habilitado: false`, la misma búsqueda hace 0 requests a ese transporte. Es lo que antes probaba el YAML del repo, y es la prueba de que se desconecta por config.
  - `::test_habilitada_por_yaml_temporal_da_leads_cc_by_sa`: con un YAML temporal que solo habilita `datos_gov_co_rues` (para aislarla de OSM y Croma), la misma búsqueda deja leads con `tipo_titular='juridica'`, con `lead_fuentes.licencia` y `cumplimiento.licencia` en `CC-BY-SA-4.0`, `url_origen` y `as_of` del header, y al menos una fila `socrata_descarga` en `costos` con el `tenant_id` del contexto.
  - `::test_naturales_se_guardan_como_conteo`: después de esa búsqueda, `busquedas.naturales_por_fuente == {"datos_gov_co_rues": 26304}`, y ninguna fila de `leads` ni de `fuente_cache` contiene datos de personas naturales.
  - `::test_mismo_nit_que_supersociedades_fusiona_por_regla_1`: una búsqueda con Supersociedades (fixture de la 002, NIT 900123456) seguida de otra con datos.gov.co (mismo NIT) deja 1 lead con 2 `lead_fuentes` y el `cumplimiento` original de Supersociedades.
- `backend/tests/integration/test_costos_repo.py::test_socrata_descarga_escribe_fila_en_costos`: el adaptador, con transporte y reloj falsos y `postgres_costos` real, deja 1 fila `socrata_descarga` por request, con `unidades == Decimal(2)`, `costo_unitario` igual a `computo_seg_usd` leído como `numeric`, `gratis=false` y el `tenant_id` del contexto.
- `backend/tests/integration/test_rls.py`: **se actualiza**. `naturales_por_fuente` de otro tenant no se ve, ya cubierto por la política de `busquedas`; el test solo suma la columna al assert.

**Tablero** *(Movido a specs/005 por D7.)*
- `backend/tests/integration/test_api_busquedas.py::test_tablero_trae_naturales_por_fuente`: con dos búsquedas completadas del tenant, la más reciente con `{"datos_gov_co_rues": 26304}`, la fila `datos_gov_co_rues` de `GET /tablero/fuentes` trae `cuenta_naturales == true` y `naturales_no_descargadas == 26304`. Si el último conteo fue `null`, trae `null`. Una fuente con `cuenta_naturales=False` (OSM) trae `cuenta_naturales == false` y `naturales_no_descargadas == null`, **nunca `0`**.
- `frontend/src/tablero/Tablero.test.tsx`:
  - `::muestra_naturales_encontradas_no_contactables`: en la columna "Naturales (no contactables)":
    - con `cuenta_naturales: true` y `26304`, muestra "26.304";
    - con `cuenta_naturales: true` y `null`, muestra "—" (falló);
    - con `cuenta_naturales: false`, muestra "no aplica".

## Fuera del alcance
- **Contacto.** El dataset no trae teléfono, correo, dirección ni web. Un lead solo de datos.gov.co queda `sin_canal_publicado` hasta que se fusione con OSM (regla 4 → revisión) o el 006 le encuentre un sitio.
- **Guardar personas naturales**, aunque sea sin contactarlas: se cuentan, no se descargan (ver Skills).
- **Paginación.** Una sola página de 5.000 (ver Decisiones técnicas).
- **Export a Dapta con atribución.** Ya lo cubre la 008: columnas `fuentes`/`licencia` desde `lead_fuentes` y línea de atribución por fuente presente. Esta spec no suma tests de export.
- **Otros países.** El dataset es solo de CO.
- **Tamaño (`ingresos_min`).** El dataset no lo trae; queda en `ignorados`.
- **El E2E de la búsqueda** que la 005 cortó: queda pendiente y la 013 lo lista.

## Decisiones técnicas

**Módulo** `backend/app/modulos/descubrimiento/`:
- `infraestructura/adaptadores/datos_gov_co_rues.py`: el adaptador, registrado en el catálogo de `infraestructura/adaptadores/__init__.py`.
- `aplicacion/camaras.py`: `cargar_camaras(ruta) -> dict[str, Camara]` y `camaras_de(departamento)`. Vive junto a `cargar_registro`, como el cargador de `actividades.yaml`; el adaptador recibe el `dict` ya cargado.

**Consultas SoQL** (verificadas contra la API real el 2026-10-17, sin token; cámara 04 y CIIU 4711):
```
GET https://www.datos.gov.co/resource/c82u-588k.json

# filas (buscar)
  $select = nit, digito_verificacion, razon_social, cod_ciiu_act_econ_pri,
            codigo_camara, organizacion_juridica, fecha_renovacion
  $where  = organizacion_juridica != 'PERSONA NATURAL'
            AND organizacion_juridica IS NOT NULL
            AND estado_matricula = 'ACTIVA'
            AND cod_ciiu_act_econ_pri = '4711'
            AND codigo_camara in('04')
            AND nit IS NOT NULL
  $limit  = 5000

# conteo de jurídicas (contar): $select = count(*), mismo $where
# conteo de naturales (buscar):  $select = count(*)
  $where  = organizacion_juridica = 'PERSONA NATURAL'
            AND estado_matricula = 'ACTIVA'
            AND cod_ciiu_act_econ_pri = '4711'
            AND codigo_camara in('04')
```
- **Lo que se midió:**
  - **Filas:** 2.015 en ~4 s (625 KB), con 2.015 NIT distintos, así que hay **una fila por NIT** y no hace falta agrupar ni colapsar. Todos tienen 9 dígitos y prefijo 8 o 9, todos con `digito_verificacion` y `razon_social`.
  - **Naturales:** `count(*)` da 26.304 en ~1 s.
  - **`contar`:** el `count(*)` tarda entre 2 y 5 s; en otras combinaciones llegó a 10 s.
- **Por qué `nit IS NOT NULL`:** de las 3.607 jurídicas activas, 1.592 no tienen `nit`. Son matrículas que no se renuevan: solo 6 se renovaron desde 2024, contra 1.311 de las 2.015 con `nit`. Sin NIT no hay dedup por la regla 1 ni `id_fiscal`, así que se filtran en el servidor.
- **`organizacion_juridica IS NOT NULL`:** en todo el país hay 144 filas activas sin ese dato. `!=` ya las excluye (comparar con null no es verdadero), pero se escribe explícito: si no se sabe la naturaleza, no entra.
- **Por qué una sola página sin `$order`:** `$order=nit` tardó más de 60-90 s y `$order=:id`, 46 s. Sin orden, `$offset` no es estable entre requests, así que no se puede paginar con seguridad. `$limit=5000` trae todo de una vez en la combinación más grande que se probó. Si llegan 5.000, `truncado`.
  - `# ponytail:` tope de 5.000 por búsqueda sin paginar. Con un ICP más ancho, el upgrade es una request por cámara (cada una más chica), no `$order`.
- **Por qué `count(*)` y no `count(distinct nit)`:** el `distinct` tardó 34 s, y como hay una fila por NIT, `count(*)` da el mismo número. `contar` es exacto: ya no es una cota alta.
- **Inyección SoQL:** los valores del `$where` salen de los criterios ya validados: el CIIU (`^\d{4}$`) y las cámaras, del YAML. Nunca se interpola texto libre, y el adaptador lanza `CriterioNoSoportado` si el CIIU no valida.
- **HTTP:** URL por constante, con override `DATOS_GOV_CO_URL` para el stub. `httpx` con **timeout de 30 s** (el máximo medido fue 10 s) y un reintento ante 502, 503, 504 o timeout, después de 1 s.
- **App token** opcional en `DATOS_GOV_CO_APP_TOKEN`: va en el header `X-App-Token` y nunca en la URL ni en los logs. Sin token, SODA limita por IP; para una búsqueda en vivo alcanza (verificado).

**Persona jurídica (principio VII), en dos capas:**
- **La autoridad es el servidor**, con `organizacion_juridica` declarada por la cámara. En el país hay 52 valores, y solo `PERSONA NATURAL` es una persona natural. Los demás son sociedades, ESAL, cooperativas y empresas unipersonales, que en Colombia son personas jurídicas (Ley 222 de 1995, art. 71).
- **El cliente es la defensa en profundidad:** descarta lo que no debió llegar, que son los casos (a), (a') y (b) a (d) del test. No lo persiste ni lo loguea, y solo lo suma a `descartados_no_juridica`.
- **Qué deja de existir respecto de la versión anterior:** la regla NIT + DV como criterio jurídico, `dominio/nit.py`, el `$group` y el colapso NIT+DV. El DV no se valida: ya no decide nada, y la cámara lo entrega con el NIT.
- **El `$select` es una lista blanca.** Las columnas de nombres y apellidos, la del representante legal y su identificación no se piden nunca, ni siquiera para las jurídicas: no hacen falta para el lead, y una consulta que no las trae no las puede filtrar.
- `tipo_titular = "juridica"`. El 006 no lo vuelve a verificar contra `croma_rues_co`, porque solo verifica los `desconocido`.

**Conteo de naturales:**
- Es una request aparte en `buscar` (página 1), después de las filas. Si las filas fallan, no se hace.
- Si el conteo falla después de los dos intentos, `naturales_no_descargadas = None` y las empresas se devuelven igual: es una métrica, y perder los leads por ella sería peor. Lo desconocido se muestra como "—", no como 0.
- Se cachea con su propia clave, y su costo se registra igual que el de las filas. **Un conteo fallido (`None`) no se cachea**: el próximo `buscar` lo reintenta y sirve las filas desde el caché.
- `EjecutarBusqueda` guarda el número en `busquedas.naturales_por_fuente`, solo para las fuentes con `cuenta_naturales=True`. Nunca guarda, por ejemplo, `{osm_overpass: null}`. El tablero toma, por fuente, el valor de la última búsqueda `completada` del tenant que lo tenga (`DISTINCT ON (fuente) … ORDER BY creada_en DESC`).
- `# ponytail:` el tablero muestra el último conteo, no una suma: dos búsquedas del mismo ICP contarían dos veces a las mismas personas. Si hiciera falta un total por tenant, se consulta por ICP.

**Mapeo a `EmpresaCruda`:**
- `nombre = razon_social`: en este dataset es la razón social de la matrícula, no el nombre de un establecimiento.
- `ciudad` = `municipio_sede` de la cámara, porque el dataset no trae municipio ni departamento.
- `direccion`, `telefono`, `email`, `web`, `geo` y los canales van en `None`. Un registro no es canal publicado (003, `test_registro_no_trae_canal_publicado`).
- `actividad = (ciiu, "CIIU")`, `licencia = "CC-BY-SA-4.0"`, y `url_origen` = la URL SODA filtrada por ese NIT: reproducible y sin datos del tenant.
- `# ponytail:` `ciudad` es la sede de la cámara, no la del negocio. Sin geo, la regla 4 del dedup nunca fusiona estos leads por nombre: van a revisión o quedan nuevos, que es el lado seguro.

**`config/camaras_co.yaml`:**
```yaml
# Cámaras de comercio (codigo_camara de c82u-588k) → departamentos DIVIPOLA que cubren.
# Una cámara no es un departamento: la 04 (Bogotá) también cubre municipios
# de Cundinamarca. Filtrar por departamento sobreincluye; no subincluye.
"04": {nombre: "Bogotá", municipio_sede: "Bogotá", departamentos: ["11", "25"]}
"14": {nombre: "Girardot", municipio_sede: "Girardot", departamentos: ["25"]}   # [VALIDAR] si también cubre 73
"21": {nombre: "Medellín para Antioquia", municipio_sede: "Medellín", departamentos: ["05"]}
# … las 58, con la tabla de la verificación (las marcadas [VALIDAR] se confirman en el paso 2)
```
- `camaras_de(departamento)` devuelve todas las cámaras cuyo `departamentos` lo incluye: 11 → `{04}` y 25 → `{04, 14, 47, 58}`.
- `# ponytail:` mapeo a nivel de departamento. Con un ICP de Cundinamarca entran los negocios de Bogotá que matriculó la 04. El upgrade es filtrar en local por municipio, pero el dataset no lo trae, así que hoy no hay cómo hacerlo.

**Costos:** `socrata_descarga` con `unidades` = segundos **del request**, medidos con el reloj inyectable. La espera de 1 s antes del reintento no se cobra, como en `overpass_query` de la 003.
- `costo_unitario = tarifas.computo_seg_usd`, cargado con `Decimal(str(v))`.
- `proveedor='datos.gov.co'`, `gratis=false` (el cómputo es nuestro aunque la API no cobre), `lead_id=None` y el `lote_id` de la corrida.
- **Hay una fila por intento, fallidos incluidos.** Es una diferencia deliberada con Croma, que en la 002 registra `unidades=0` en un intento fallido: Croma cobra créditos solo por respuesta exitosa, mientras que acá lo que se cobra es nuestro cómputo, y ese se gasta igual cuando la request falla.
- `costo_maximo_llamada = 2 requests × 2 intentos × 30 s × computo_seg_usd`.

**Caché:** `fuente_cache` con `proveedor='datos.gov.co'`, `endpoint='c82u-588k'`, `hash_params` de los parámetros SoQL ordenados y `as_of` del header. Las filas, el conteo de naturales y `contar` usan claves distintas.
- Se guardan **las filas ya filtradas por el cliente**, no la respuesta cruda. Así, aunque el servidor dejara pasar algo, el caché no lo guarda (`test_cache_no_guarda_lo_descartado`).
- A diferencia de Overpass (003), esta respuesta se puede cachear: no trae teléfono, correo, dirección ni personas naturales.

**Sin red en tests:** la fixture `autouse` `sin_red`, en `backend/tests/unit/conftest.py` y `backend/tests/contratos/conftest.py`, parchea `socket.socket.connect` y `connect_ex`. Permite loopback (`127.0.0.0/8`, `::1`) y sockets Unix, y para todo lo demás lanza `RedBloqueadaEnTests`.
- `integration/` queda afuera porque necesita Postgres (que puede no estar en loopback en CI), pero sus transportes HTTP son falsos.
- `# ponytail:` stdlib en lugar de `pytest-socket`, para no sumar una dependencia por 15 líneas.
- `# ponytail:` no bloquea DNS, porque `getaddrinfo` sale por el resolver de C y no pasa por `socket.connect`. Una resolución se filtra, pero la conexión no. Si hiciera falta, se parchea también `socket.getaddrinfo`.

**Selección de registro:** la CLI lee `FUENTES_YAML` del entorno (por defecto `config/fuentes.yaml`) y se lo pasa a `cargar_registro`. La API no la lee: en Railway siempre corre el YAML del repo.

**Atribución:** la define la 005 en `v_atribuciones`, por fuente presente en `lead_fuentes` del tenant, también si la fuente hoy está desconectada (sus filas siguen en la base). El `VALUES` de esa vista ya trae `datos_gov_co_rues`, y lo cubre `test_tablero_atribucion_solo_de_fuentes_presentes[osm_y_datos_gov]` de la 005, que siembra `lead_fuentes` sin depender de este adaptador.

## Plan de tareas (TDD, en orden)
1. **Corregir las skills.** Va primero porque el `lead` las carga antes de escribir el adaptador.
   - `fuentes-publicas`, fila de `datos_gov_co_rues` (línea 39): dataset `c82u-588k`, `filtros: [ciiu, departamento]`, jurídica por `organizacion_juridica` en el servidor.
   - `fuentes-publicas`, línea 56: `tipo_titular` **no** sale de `clase_identificacion`, porque la clase NIT incluye personas naturales; sale de `organizacion_juridica`.
   - `cumplimiento-datos`, regla 1 (línea 16): la misma corrección.
   - `cumplimiento-datos`, regla 4 (línea 19): una nota de que una fuente que permite filtrar en el servidor cuenta a las naturales en lugar de guardarlas.
2. **`config/camaras_co.yaml`:** `test_camaras_co.py` en rojo → verde. Las cámaras marcadas `[VALIDAR]` se confirman con una consulta a la API (`$select=codigo_camara,camara_comercio&$group=codigo_camara,camara_comercio`) y con el sitio de Confecámaras.
3. **Sin red:** `test_conexion_saliente_falla` en rojo → verde, junto con `test_loopback_sigue_permitido`, que es la guarda y se pone en rojo a mano para comprobarlo. Después se corre la suite entera de `unit/` y `contratos/` para comprobar que la fixture no rompe nada existente.
4. **Fixtures sintéticas y filtro jurídico:** `test_query_filtra_juridicas_en_servidor`, `test_select_no_pide_columnas_de_personas`, `test_cliente_descarta_lo_que_no_debio_llegar` y `test_descartados_no_se_loguean` en rojo → verde. El **advisor revisa estos tests antes de aceptarlos**, porque son el principio VII.
5. **Conteo de naturales:** los campos aditivos del resultado de página y `cuenta_naturales` en `MetaFuente`, `test_campos_aditivos_del_resultado` en el contrato, `test_conteo_de_naturales_sin_filas` y `test_conteo_de_naturales_falla_y_las_filas_siguen` en rojo → verde.
6. **Resto del adaptador:** cámaras, mapeo, `as_of`, truncado, página 2, `contar`, costos, fallo, caché (con `test_conteo_fallido_no_se_cachea`), token y URL en rojo → verde. Después `test_socrata_descarga_escribe_fila_en_costos`. El **advisor revisa los tests de costos**.
7. **Registro y contrato:** cambio de `dataset`/`filtros`/`trae` y `habilitado: false → true` en `fuentes.yaml`, en el mismo commit, alta en el catálogo, `test_registro.py` y `test_seleccion_fuentes.py` actualizados, suite de contrato con `[datos_gov_co_rues]`: rojo → verde. Todo test de la 003 o la 005 que arme el registro desde el YAML del repo (por ejemplo, si `test_icp_colombia_completo_usa_las_dos_fuentes` lo hace) pasa a esperar también `datos_gov_co_rues` en este paso; los que usan un registro en memoria no cambian.
8. **Migración `busquedas.naturales_por_fuente`**, CLI con `FUENTES_YAML` e integración `test_conectar_desconectar.py` (con `test_naturales_se_guardan_como_conteo`) y `test_rls.py`: rojo → verde.
9. ~~**Tablero:** `test_tablero_trae_naturales_por_fuente` y `Tablero.test.tsx` en rojo → verde.~~ *(Movido a specs/005 por D7.)*
10. **Una corrida real**, avisada antes, con el YAML del repo (CO/4711/11), sin token y contra Postgres de desarrollo. Se anotan los segundos de cada request, las filas, los descartados, las naturales y el `as_of`. Si la forma difiere de la fixture, se corrige la fixture y se vuelve al paso 6. La respuesta real **no se commitea** (trae NITs reales), y solo se anotan conteos.
11. **`docs/arquitectura-backend.md`:** cómo conectar o desconectar una fuente, con este adaptador como ejemplo, y por qué la persona natural se filtra en el servidor y se cuenta. Es lo primero que se recorta.

**Cuándo cortar:** si a la 1,5 h falta algo, se corta en este orden, y cada corte baja exactamente estos tests:

| Orden | Se corta | Test que se baja | Queda en su lugar |
|---|---|---|---|
| 1 | Paso 11 (doc completa) | — | Un párrafo de 5 líneas en `docs/arquitectura-backend.md`, en el mismo PR: cómo se conecta y se desconecta una fuente, y por qué la natural se cuenta. Así el principio X no bloquea CI. El detalle lo consolida la 013. |
| 2 | ~~Columna de naturales en el tablero~~ | Movido a specs/005 (D7) | — |
| 3 | `FUENTES_YAML` en la CLI | `test_respeta_fuentes_yaml_del_entorno` | En la demo se edita `habilitado` en `config/fuentes.yaml` local y no se commitea. `test_conectar_desconectar.py` sigue pasando, porque le pasa la ruta a `cargar_registro` directamente. |
| 4 | Las 58 cámaras | `test_yaml_real_cubre_58_camaras_y_33_departamentos` | Solo las cámaras de 11 y 25 (04, 14, 47, 58), más `test_bogota_y_cundinamarca`. Un departamento sin cámara lanza `CriterioNoSoportado`, el lado seguro. |
| 5 | Caché | `test_cache_hit_no_hace_request`, `test_cache_no_guarda_lo_descartado`, `test_conteo_fallido_no_se_cachea` | Una request por búsqueda. La API es gratis, y el costo de cómputo queda en `costos` igual. Sin caché no hay nada guardado que filtrar. |

**No se cortan:** el filtro jurídico en el servidor y su defensa en el cliente, la lista blanca del `$select`, sus tests y el de logs (principio VII); el conteo de naturales en `busquedas`; la suite de contrato; `habilitado: true` en el repo y su par deshabilitado por YAML temporal; la fixture sin red; el costo por intento (principio VIII); el token fuera de los logs; y la fila de `cumplimiento` con CC BY-SA. La atribución vive en la 005, dentro de su mínimo para la demo.

## Riesgos
- **Calidad de `organizacion_juridica`:** lo declara cada cámara. Si una matriculara a una persona natural con otra organización jurídica, entraría. No es una heurística nuestra: es el dato oficial de la naturaleza de la matrícula, el mismo que decide si la persona está bajo la Ley 1581. La corrida del paso 10 revisa a mano 20 razones sociales al azar, contando cuántas parecen un nombre propio sin forma societaria (sin `S.A.S.`, `LTDA`, `S.A.` ni similares), y anota solo ese conteo. Si aparece alguna, se para y se revisa.
- **Esquema o datos que cambian:** Confecámaras actualiza el dataset y puede renombrar columnas. La suite corre con fixture y no lo detectaría. La corrida del paso 10 es el chequeo, y el `as_of` del header queda en `cumplimiento`.
- **Latencia de SODA:** los `count(*)` variaron entre 1 y 10 s, y cualquier `$order` pasa el minuto. Con 30 s de timeout y un reintento, el peor caso de `buscar` son ~2 min, y por eso `costo_maximo_llamada` lo refleja. Si en la demo tarda, el caché del ensayo previo la sirve.
- **Throttling de SODA sin token:** en la verificación no apareció. Si aparece en la demo, se carga `DATOS_GOV_CO_APP_TOKEN` en el entorno local; nunca en el repo.
- **Leads sin contacto:** como fuente sola de descubrimiento, todo lo que trae es `sin_canal_publicado`. Aporta volumen y cobertura de pymes que Supersociedades no tiene, no contactabilidad: esa la dan OSM y `sitio_web` (006). No llena el embudo de llamadas por sí sola. Se ve en el tablero (columna `con_telefono` de la 006) y no se esconde.
- **Sobreinclusión geográfica:** con un ICP de Cundinamarca entran negocios de Bogotá (cámara 04). El encaje ICP del 006 puede bajarlos, pero el conteo de la vista previa los incluye.
- **Share-alike en el export.** La base derivada mezcla datos CC BY-SA; exportarla con atribución y licencia lo cubre la 008 (`fuentes`/`licencia` desde `lead_fuentes`). La 008 depende de la 005, que depende de esta spec (orden 002 → 003 → 011 → 004 → 005), así que no hay export de datos.gov.co sin este slice implementado antes.
- **Tiempo:** el PRD le da ~1,5–2 h, sin holgura. Completa, con el conteo de naturales y las cámaras, son ~2 h; los cortes de la tabla la dejan en ~1,5 h sin tocar el principio VII.
