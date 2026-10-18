# Tasks: 003 — OSM Overpass, normalización común y dedup en 4 niveles

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Prerequisites**: ya no es "002 mergeado entero". Cada tarea [MIN] dice de qué tareas de la 002 depende (IDs de `specs/002-puertos-registro-supersociedades/tasks.md` en `main` `168f4b9`), o "ya" si arranca hoy. Las preguntas P1–P11 están cerradas en `plan.md` (sección Preguntas abiertas), contra el plan 002 en `89d3e59` y las enmiendas de la spec 003 §Puertos.

> Formato de `/speckit-tasks` aplicado a mano (`setup-plan.sh` no resuelve el feature).

**Formato**: `- [ ] TNNN [MIN?] [P?] [Paso] Descripción — 002: <IDs> | ya`
- **[MIN]**: mínimo funcional. Sin esa tarea, OSM no devuelve leads guardados por tenant que se vean en el tablero. Todo lo demás está en la Fase Pulido, al final.
- **[P]**: se puede hacer en paralelo (otro archivo, sin dependencia con una tarea abierta).
- **[Paso n]**: el paso del "Plan de tareas" de la spec.
- **`002: …`**: las tareas de la 002 que tienen que estar en verde antes. **ya** = solo depende de lo que la 002 ya tiene hecho (T001–T019).
- Las tareas partidas conservan su ID en [MIN], con el alcance reducido; el resto va a Pulido con el mismo ID y una `p` al final (por ejemplo, `T039p`).
- Cada **Rojo** se corre y se ve fallar **por la razón correcta** (aserción, no `ImportError` de un archivo que falta) antes de su **Verde**. Un test que nace verde no se acepta: se rompe a propósito la implementación para verlo fallar. Esto vale igual en [MIN] y en Pulido.

**Lo que no se negocia en [MIN]:** TDD con rojo real en cada tarea, aislamiento por tenant, sin secretos y el rol `app_rt` intacto. El [MIN] no trae migración, así que `app_rt` y la `0002` no se tocan.

**Advisor:** los documentos tienen una sola vuelta. Los hallazgos MEDIUM o menores se anotan y se sigue; solo frena un HIGH de tenant, secretos o rol. Los tests se siguen revisando antes de su Verde.

**Qué queda fuera del [MIN] y por qué:**
- **Contacto (teléfono, email, web):** el [MIN] no lo mapea ni lo guarda. Guardarlo exige el bloque completo de cifrado (Cifrador, columnas, `CHECK` de canal, catálogo y logs). No guardar contacto es la forma segura de cumplir el principio VI mientras tanto. `EmpresaCruda` no suma los campos de contacto hasta Pulido, así que no hay por dónde filtrarlo.
- **Dedup de OSM:** OSM no trae `id_fiscal`, y el `UNIQUE (tenant_id, pais, id_fiscal)` de la 002 no deduplica `NULL`. Por eso **dos búsquedas iguales duplican los leads de OSM** hasta que llegue el bloque de dedup de Pulido. Es el costo principal del corte.
- **datos.gov.co** no es de esta slice: su adaptador está desconectado (`habilitado: false`) y lo reconecta otra.

Comando de la suite: `cd backend && uv run pytest -q && uv run lint-imports`.

---

## Fase 1: Puerta

- [ ] T001 [MIN] Puerta por tarea: antes de cada tarea que dice `002: …`, esta rama se pone al día con la rama de la 002, con esas tareas en verde. Las tareas "ya" arrancan sin esperar. — 002: según cada tarea

---

## Fase 2: Selección de fuentes (Paso 2)

Sin esta fase, OSM nunca corre: un ICP trae `ciiu`, y OSM declara `filtros: [ciudad, tipo_negocio]`. El `cubre()` estricto del 002 lo descarta, y sin el mapeo `ciiu → tipo_negocio` no hay query.

- [ ] T012 [MIN] [P] [Paso 2] **Rojo:** `backend/tests/unit/descubrimiento/test_seleccion_fuentes.py::test_actividades_yaml_real_carga_y_mapea_4711`. — ya (002 T009)
- [ ] T013 [MIN] [Paso 2] **Verde:** `backend/config/actividades.yaml` (4711, 5611, 4752, contenido de la spec) + `cargar_actividades` en `aplicacion/registro.py`. — ya
- [ ] T014 [MIN] [Paso 2] **Rojo:** `::test_icp_colombia_completo_usa_las_dos_fuentes`, `::test_icp_sin_ciudad_ignora_osm_por_geografia`, `::test_ciiu_sin_mapeo_ignora_osm`, `::test_icp_fuera_de_colombia_solo_usa_osm[BR|PE]` (parametrizado; con las `MetaFuente` del `fuentes.yaml` real: `seleccionadas.keys() == {"osm_overpass"}` e `ignoradas == {"croma_supersociedades_co": "pais"}`) y `::test_criterio_no_declarado_no_llega_al_adaptador`. — ya (002 T007)
- [ ] T015 [MIN] [Paso 2] **Verde:** `seleccionar_fuentes(metas: Iterable[MetaFuente], criterios, actividades) -> tuple[dict[str, CriteriosICP], dict[str, str]]` (`seleccionadas`, `ignoradas`) en `dominio/seleccion.py`. Recibe `MetaFuente`, no `Registro` (tipo de `aplicacion`; contrato `layers`, 002 plan:31). País con `cubre()` → actividad → geografía. Por fuente, `CriteriosICP.filtros` queda reducido a las claves que declara (criterio presente = clave del mapeo, nunca clave con `None`; `ciiu` → `tipo_negocio` como `tuple` de etiquetas OSM). Motivos `pais`, `sin_mapeo_actividad`, `sin_geografia`. — ya
- [x] T016a [MIN] [Paso 2] **Rojo (test del 002 que se actualiza):** `backend/tests/unit/descubrimiento/test_dominio.py::test_cubre`, el caso "falso con un filtro fuera de `meta.filtros`" pasa a esperar **verdadero** (falla por assert con el `cubre()` estricto del 002). — 002: T039 (se espera para no cambiarle `cubre()` a la 002 mientras escribe `EjecutarBusqueda`)
- [x] T016b [MIN] [Paso 2] **Verde:** `cubre()` queda solo con el país (se saca `set(filtros) ⊆ meta.filtros`); `EjecutarBusqueda` le pasa `[m for _, m in registro.fuentes]` a `seleccionar_fuentes`, deja de usar el `cubre()` estricto y deriva `sin_fuente_para` de `seleccionadas` vacío. `test_sin_fuente_para_el_pais_se_reporta` (002 T038) se corre y sigue verde; si la derivación está mal, falla ahí. Va **después del Rojo de T049**, para que T049 nazca rojo. — 002: T038, T039

**Checkpoint**: `test_seleccion_fuentes.py`, `test_cubre` actualizado y el resto de la suite del 002 verdes.

---

## Fase 3: Adaptador OSM mínimo (Paso 7)

El adaptador arranca ya con transporte falso y un `RegistroCostos` falso. Si el test `test_registro_adaptadores.py::test_todo_adaptador_de_registro_esta_declarado` (002 T036) ya existe cuando nace `osm_overpass.py`, queda en rojo desde T038 hasta T048. Es el único rojo permitido fuera del test en curso, y por eso T038 y T048 van seguidas. Si todavía no existe, no hay ventana de rojo.

- [ ] T037 [MIN] [Paso 7] **Rojo:** `backend/tests/fixtures/osm/` (respuestas sintéticas: nodo, `way` con `center`, sin `name`; datos inventados) y `backend/tests/unit/descubrimiento/test_osm_overpass.py::test_query_acotada_con_timeout_y_tope`, `::test_envia_user_agent_identificable`. — ya
- [ ] T038 [MIN] [Paso 7] **Verde:** `infraestructura/adaptadores/osm_overpass.py` con el constructor del 002 (`meta`, `RegistroCostos`, transporte, `costo_unitario`, `lote_id`; 002 plan:150) más `url`. Valida los criterios contra `meta.filtros` antes de cualquier request. Query única. URL por constante, con override `overpass_url` de `Settings`. User-Agent `dapta-reto-30x/<versión>` con la URL del repo desde config. `httpx` con timeout de 30 s. — ya (002 T007)
- [ ] T039 [MIN] [Paso 7] **Rojo:** `::test_mapea_elemento_a_empresa_cruda` (nombre, ciudad, dirección, `url_origen` del elemento, `as_of`, `tipo_titular == "desconocido"`, `adaptador.meta.licencia == "ODbL"`; sin `web` ni contacto) y `::test_elemento_sin_nombre_se_descarta`. — ya
- [ ] T040 [MIN] [Paso 7] **Verde:** mapeo a la `EmpresaCruda` del 002 tal como está (sin campos nuevos); el elemento sin `name` no sale; `PaginaEmpresas(empresas, total=None)`. — ya
- [x] T041 [MIN] [Paso 7] **Rojo:** `::test_registra_segundos_de_cada_intento` (1 request → 1 fila `overpass_query` antes de devolver) y `::test_fallo_se_reporta_sin_tragarlo` (500 → `FuenteNoDisponible`, 1 fila escrita, el mensaje sin el cuerpo). — ya (RegistroCostos falso; 002 T007)
- [x] T042 [MIN] [Paso 7] **Rojo:** `backend/tests/integration/test_costos_repo.py::test_overpass_query_escribe_fila_en_costos` (`postgres_costos` real, `unidades == Decimal(2)`, `costo_unitario` como `numeric`, `tenant_id` del contexto). Se escribe antes del Verde de T044, para que nazca rojo. — 002: T024, T025
- [x] T043 [MIN] [Paso 7] **Advisor** revisa T041 y T042 (costos por intento, sin espera cobrada, `Decimal`) antes de implementar. — ya (T042 se suma a la revisión cuando exista)
- [x] T044 [MIN] [Paso 7] **Verde:** `RegistroCostos.registrar` con `overpass_query` por intento **antes de devolver o lanzar**; `FuenteNoDisponible` sin el cuerpo de la respuesta. La tarifa llega por constructor como `Decimal`; en la raíz de composición la resuelve la 002 (002 plan:150). `lote_id = busqueda_id`, y `ts` lo pone la base (002 plan:286, :291). Sin limitador ni reintento: van a Pulido. — ya (la parte de integración pasa cuando la 002 tenga T025)

Nota de proceso: T044 (verde) se implementó antes de que el advisor revisara T041/T042 (T043); la revisión llegó después y aprobó con LOW, resueltos en 8dc8567. T042 nació verde porque T044 ya estaba: se aceptó con dos sabotajes con nombre (`sin_fila_de_costos`, `unidades_fijas_en_1`), aplicados y revertidos, ambos en rojo por `AssertionError`.

Dudosa: **limitador y reintento a Pulido.** El [MIN] hace una sola query por búsqueda, así que no hay ráfaga contra Overpass. El fallo se reporta y la búsqueda sigue con el aislamiento por fuente del 002.

**Checkpoint**: `test_osm_overpass.py` verde; `test_costos_repo.py` verde cuando la 002 tenga T025.

---

## Fase 4: Registro y contrato (Paso 8)

- [ ] T047 [MIN] [Paso 8] **Rojo:** `backend/tests/unit/descubrimiento/test_registro.py::test_osm_overpass_carga_con_el_catalogo_real`. Con `fuentes.yaml` real y el catálogo real, `osm_overpass` tiene que estar en `registro.fuentes` y no en `sin_implementacion`. Falla por assert mientras no esté en el catálogo. Es un test nuevo, porque `test_carga_config_fuentes_yaml_real_sin_error` sigue en `xfail(strict)` hasta 002 T031 (Croma); su cambio va a `T047p`. — ya (002 T009)
- [ ] T048 [MIN] [Paso 8] **Verde:** `osm_overpass` en el catálogo de `infraestructura/adaptadores/__init__.py`. `config/fuentes.yaml` no cambia (la entrada ya está con `habilitado: true`). El `xfail(strict)` del 002 sigue en xfail, porque Croma todavía falta. Si 002 T034 ya existe, `test_hay_fabrica_para_cada_clave_del_catalogo` pasa a rojo hasta T048b. Choca con 002 T031 en una línea del mismo dict: se resuelve dejando las dos claves. — ya
- [ ] T048b [MIN] [Paso 8] **Verde:** fábrica `osm_overpass` en `backend/tests/contratos/fabricas.py` (`fabrica(transporte, registro)`, con transporte falso sobre la fixture de `tests/fixtures/osm/`). Corren los tres tests de contrato con `[osm_overpass]`; `::test_rechaza_criterio_no_soportado[osm_overpass]` usa la centinela `"__criterio_inexistente__"` del 002 (002 plan:160). — 002: T034, T035

Dudosa: **T048b es [MIN] aunque el flujo funcione sin ella**, porque todo adaptador pasa la suite de contrato de su puerto (CLAUDE.md). La 002 pone T034/T035 después de Croma solo porque su catálogo está vacío. Con `osm_overpass` en el catálogo (T048), T034 y la fábrica en `fabricas.py` se pueden adelantar con OSM como primera clave, y la fábrica de Croma se suma después. Lo decide el coordinador; si no se adelantan, T048b espera.

**Checkpoint**: `test_registro.py` verde (con el `xfail` del 002 intacto); suite de contrato verde para `osm_overpass` cuando exista.

---

## Fase 5: Búsqueda con OSM, guardada por tenant (Paso 9)

- [x] T049 [MIN] [Paso 9] **Rojo** *(advisor antes del Verde: tenant)*: `backend/tests/integration/test_busqueda_osm.py::test_osm_guarda_leads_en_el_tenant`. `EjecutarBusqueda` real con el catálogo real, OSM con transporte falso sobre la fixture, `postgres_costos` y `repositorio_leads` reales, y un ICP `CO` + `ciiu=4711` + `ciudad`. Como tenant A, N leads de la fixture, cada uno con su fila de `cumplimiento` (`fuente='osm_overpass'`, licencia `ODbL`, `tipo_titular='desconocido'`) y una fila de `costos` `overpass_query`. Como tenant B, 0 leads, 0 `cumplimiento` y 0 `costos`. Nace rojo por assert, con 0 leads de A, porque el `cubre()` estricto descarta OSM por `ciiu`. Por eso va antes de T016b. El assert de B nace verde por la RLS del 002 (T017/T019, ya visto rojo allá); como sabotaje con nombre, se corre la búsqueda dentro de la unidad de trabajo de B y el assert de A tiene que fallar. — 002: T021, T025, T039
- [x] T051 [MIN] [Paso 9] **Verde:** lo que T049 exija en `aplicacion/ejecutar_busqueda.py` sobre T016b: `obtener_o_crear_lead(e, meta.licencia)` para cada `EmpresaCruda` de OSM, con el aislamiento de `LimiteFuenteAgotado`/`FuenteNoDisponible` por fuente del 002 (002 plan:295). Sin dedup nueva: la del 002 por `(pais, id_fiscal)` no aplica a OSM. Ningún log con datos del lead. — 002: T039

Nota de proceso: T049 nació verde porque T016b se hizo antes (el orden de esta tarea pedía lo contrario). Se aceptó con los sabotajes con nombre `seleccion_estricta` y `tenant_cruzado`, ambos en rojo por `AssertionError`. T051 sin cambios: cubierta por T016b, verificada por T049 (sin logs con datos del lead).

**Checkpoint**: suite completa verde.

---

## Fase 6: CLI y corrida real (Paso 10)

- [x] T052 [MIN] [Paso 10] **Rojo + Verde:** `backend/tests/unit/test_cli.py::test_ciudad_llega_a_los_criterios`. Con `catalogo={"osm_overpass": FuenteFalsa}`, `--ciudad Bogotá` llega en `criterios.filtros["ciudad"]`. El rojo es por mutación: primero `--ciudad` entra en `argparse` sin pasar a los criterios, y falla el assert. Después, el verde en `app/cli.py`. El resumen detallado va a `T052p`. — 002: T040, T041 (en `main`, T041 ya lee `tarifas.yaml` con `Decimal(str(v))`)
- [ ] T053 [MIN] [Paso 10] **Una** corrida real contra Overpass (Bogotá, 4711), **avisada antes**. Se anotan los segundos, los elementos y el `name` real de la relación de Bogotá, sin copiar ningún dato de contacto. Si difiere de la fixture, se corrige la fixture y se vuelve a la Fase 3. Dudosa: es [MIN] porque la fixture es sintética, y sin una corrida real no está probado que OSM devuelva leads. — 002: T041 (vía T052)
  **Decisión del dueño (2026-10-18): T053 se difiere al primer deploy en Railway.** Se valida desde la pantalla "Nueva búsqueda" de la 005 (Bogotá, CIIU 4711), anotando los segundos de la fila `overpass_query`, los elementos devueltos y si el `name` de Bogotá coincide con la fixture. Queda como deuda explícita, no bloquea el PR del [MIN].

---

## Fase 6b: nombre y dirección cifrados para titulares no jurídicos (enmienda 2026-10-18)

Decisión del dueño: `tipo_titular != 'juridica'` guarda `nombre` y `direccion` cifrados; hoy `repositorio_leads.py` los guarda en claro (los leads OSM del [MIN]). Es [MIN] porque el principio VI no admite persistir el nombre y el domicilio de un posible comerciante en claro. **Arrastra del Pulido solo lo mínimo para cifrar** (T002, T003, T017, T018: dependencias, import-linter y `Cifrador`); `telefono`/`email` y el resto de P1 siguen en Pulido. **DDL aprobado por el dueño el 2026-10-18**; decisiones del mismo día: `url_origen` de OSM en claro, y sin backfill (leads de prueba).

- [ ] T002 [MIN] y T003 [MIN] (suben de P1 sin cambios): `cryptography` en `pyproject.toml` + `uv.lock` con `pip-audit` limpio, y `import-linter` con `cryptography` fuera del dominio. — ya
- [ ] T017 [MIN] [P] [Paso 3] **Rojo:** `backend/tests/unit/seguridad/test_cifrador.py` (sube de P1 sin cambios: ida y vuelta, nonce distinto, AAD de otra columna, HMAC, falla sin `cifrado_key`) + `::test_aad_de_nombre_y_direccion_no_se_intercambian` (un valor cifrado para `leads.nombre_cifrado` no descifra como `leads.direccion_cifrada`, ni al revés) + `::test_aad_de_otra_fila_no_descifra` (otro `lead_id` u otro `tenant_id` lanza `InvalidTag`). El rojo es un `assert`/`pytest.raises(InvalidTag)`, no un `ImportError`: se crea primero un `cifrado.py` vacío con la firma y los asserts fallan. — ya
- [ ] T018 [MIN] [Paso 3] **Verde:** `app/seguridad/cifrado.py` (AES-256-GCM, AAD `leads.<columna>:<tenant_id>:<lead_id>`, HKDF; API `cifrar(columna, valor, tenant_id, lead_id)`), `catalogo_sensibles.py` (con `CIFRADAS` y `CONDICIONALES`), `cifrado_key` en `Settings` y `ConfigInvalida`. `CIFRADO_KEY` en `.env.example` y en la doc de variables. — T017
- [ ] T056a [MIN] [Paso 4] **Rojo (INSERT crudo):** `test_dedup_repo.py::test_check_nombre_segun_tipo_titular` (casos de la spec; nace rojo por assert: sin `CHECK`, el `INSERT` de un `desconocido` con `nombre` en claro no falla, y `nombre_cifrado` no existe: se agrega primero la migración **sin** `CHECK` como preparación, igual que T023a). Además, se actualizan los `INSERT` crudos que hoy dejan `desconocido` con `nombre` claro y romperían: `test_leads_repo.py:49`, `test_rls.py:46` y `:69` (pasan a `tipo_titular='juridica'`), y `test_leads_repo.py:91` y `test_busqueda_osm.py:82` leen por el repositorio, no por SQL, en la lectura de `nombre`. — T018
- [ ] T056b [MIN] [Paso 4] **Migración (DDL de `plan.md` aprobado 2026-10-18):** `supabase/migrations/0003_leads_cifrado_nombre_direccion.sql` con `nombre` nullable, `nombre_cifrado`, `direccion_cifrada` los dos `CHECK ... NOT VALID` (con `octet_length(nombre_cifrado) > 28`) y los dos bloques `DO` con `VALIDATE CONSTRAINT` que atrapan `check_violation` (DDL final en `plan.md`); `app/modelos.py` al día (drift vacío). Verde de T056a. **Rojo propio antes:** `test_migraciones.py::test_checks_de_titular_quedan_convalidados_desde_vacio` (`convalidated = true` en los dos, sobre `base_vacia`); nace rojo con la migración sin los bloques `DO`. `migrar_local.sh` dos veces desde vacío (`test_migrar_local_desde_vacio_dos_veces_sin_drift`). — T056a
- [ ] T056c [MIN] [Paso 4] **Rojo:** `test_cifrado.py::test_nombre_y_direccion_de_no_juridica_van_cifrados` (lead `desconocido` y `natural`, con control `juridica`), `::test_nombre_y_direccion_en_claro_solo_para_juridicas` y `::test_nombre_solo_se_lee_por_el_repositorio`. Rojo por assert contra el repositorio que sigue guardando en claro (`nombre IS NULL` falla). Sabotajes con nombre: `nombre_en_claro_si_desconocido`, `select_suelto_de_nombre`. — T056b
- [ ] T056d [MIN] [Paso 4] **Advisor** revisa T056a y T056c **antes del verde** (los `CHECK`, el AAD por columna, tenant y lead, el paso a claro al subir a jurídica y que el rojo es por `assert`, no por columna inexistente). Revisión de juicio: cifrado y RLS (agente `lead.md`). — T056c
- [ ] T056e [MIN] [Paso 4] **Verde:** `repositorio_leads.py`: `obtener_o_crear_lead` genera el `id` del lead en la app antes del `INSERT` y cifra `nombre` y `direccion` (AAD columna + tenant + lead) si `tipo_titular != 'juridica'`; la lectura de `Lead` descifra. `aplicar_fusion` con la regla (a)/(b)/(c) de la spec llega con el dedup (T036); hasta entonces, T056e solo cubre creación y lectura. — T056d
- [ ] T056e2 [MIN] [Paso 9] **Rojo y verde de `hide_parameters`:** `backend/tests/unit/test_db.py::test_engine_oculta_los_parametros_en_los_errores` (un `INSERT` que viola un `CHECK` con `nombre='Tienda Doña Rosa'`: `str(excepción)` no contiene el nombre). Rojo real por `assert` (hoy SQLAlchemy imprime `[parameters: …]`); verde: `create_engine(url, connect_args=…, hide_parameters=True)` en `backend/app/db.py::crear_engine`. El `DETAIL` de Postgres (fila fallida) lo cubre T056f/T056g. — T056e
- [ ] T056f [MIN] [Paso 9] **Rojo:** `test_cifrado.py::test_contacto_no_aparece_en_logs` ampliado (nombre y dirección sintéticos de la fixture, `capsys`, y una `CheckViolation` forzada con un `desconocido` en claro: ni `caplog`, ni `capsys`, ni `str(excepción)` traen el nombre; incluye el `DETAIL` de Postgres) y `::test_contacto_no_queda_en_claro_en_columnas_no_catalogadas` con `leads.nombre`/`leads.direccion` `NULL` para OSM. Rojo por `assert` con el repositorio todavía sin cifrar (si T056e ya está, se corre con el sabotaje `log_del_nombre`: un `logging.debug` con el nombre en `EjecutarBusqueda`, visto fallar y revertido). — T056e
- [ ] T056g [MIN] [Paso 9] **Verde:** el repositorio atrapa `DBAPIError` y relanza `ErrorPersistencia` con mensaje fijo y `from None` (el `DETAIL` de Postgres trae la fila entera); `EjecutarBusqueda`/CLI sin nombre ni dirección en logs, trazas, `capsys` ni mensajes de error; si T056f ya pasó con el sabotaje, esta tarea es la reversión documentada. — T056f
- [ ] T056 [MIN] **Migración de validación `0005` (sin backfill: decisión del dueño, 2026-10-18; el script `cifrar_leads_existentes.py` sale del [MIN]):** `supabase/migrations/0005_validar_checks_leads.sql` (`VALIDATE CONSTRAINT` de los dos `CHECK` sin condición, DDL en `plan.md`). **Rojo primero** (`test_migraciones.py`): el test siembra con `MIGRACIONES` apuntando a un directorio temporal con solo `0001`–`0002`, inserta un `desconocido` en claro (todavía no hay `CHECK`, así que el `INSERT` no falla), aplica la `0003` (queda `NOT VALID`, `convalidated = false`) y verifica que la `0005` **falla** (el lead sigue en claro; la versión no queda registrada). Segundo caso: sin filas en claro, `0001`–`0003` y `0005` pasan y `convalidated = true`. Sembrar con el `CHECK` ya puesto no sirve: el `INSERT` en claro falla por `IntegrityError`, no por `assert`. — T056b

**Checkpoint**: `test_cifrador.py`, `test_cifrado.py` (los tres nuevos), `test_dedup_repo.py::test_check_nombre_segun_tipo_titular` y la suite completa verdes; `migrar_local.sh` dos veces desde vacío.

---

## Fase 7: Cierre del mínimo

- [ ] T055 [MIN] Cierre **sin T053** (diferido por decisión del dueño, 2026-10-18; se deja como deuda explícita en el PR) (incluye la Fase 6b): `uv run pytest -q`, `uv run lint-imports`, `scripts/migrar_local.sh` dos veces desde vacío. PR del [MIN], con la lista de Pulido como deuda. Se repite al cerrar Pulido. — ya

---

## Fase Pulido

Va después del [MIN], en este orden de bloques. **El bloque P1 entra entero o no entra:** ningún dato de contacto se mapea ni se guarda hasta que T018, T026 y T050 estén verdes. Los IDs y los textos son los de la versión anterior de este archivo (commit `47b35b9`), salvo lo que se aclara en cada línea.

### P1: contacto cifrado (Pasos 1, 3, 4 y 7)

- [ ] T002 [P] `phonenumbers` en `backend/pyproject.toml` + `uv.lock`; `pip-audit` limpio. (`cryptography` ya entró en el [MIN], Fase 6b.)
- [ ] T003 [P] Contrato de import-linter: `phonenumbers` permitida en `descubrimiento.dominio`. (`cryptography` y `httpx` fuera del dominio: Fase 6b.)
- [ ] T008 [Paso 1] **Rojo:** `test_normalizacion.py::test_telefono_a_e164`, `::test_mismo_numero_con_y_sin_indicativo_da_el_mismo_e164`.
- [ ] T009 [Paso 1] **Verde:** `a_e164(valor, region)` con `phonenumbers.parse` + `is_valid_number`.
- T017 y T018: pasaron al [MIN] (Fase 6b). Lo que queda para Pulido de ellas: los tests de HMAC (`test_hmac_es_determinista_y_distinto_de_la_clave_de_cifrado`, `test_mismo_numero_con_y_sin_indicativo_da_el_mismo_hmac`) y `hmac_telefono`, que se suman a `test_cifrador.py` y `cifrado.py` junto con T008/T009.
- [ ] T023a [Paso 4] **Preparación:** `supabase/migrations/0003_osm_dedup.sql` (a mano) con las columnas nuevas de `leads` **sin** `CHECK`; btree no únicos `(tenant_id, dominio)` y `(tenant_id, telefono_hmac)`. No toca `costos` (002 plan:210).
- [ ] T023 [Paso 4] **Rojo:** `test_dedup_repo.py::test_canal_null_si_y_solo_si_dato_null` y `::test_check_de_canales` (INSERT crudo).
- [ ] T024 [Paso 4] **Verde:** los `CHECK` de canal y de dato ⇔ canal.
- [ ] T025 [Paso 4] **Rojo:** `test_cifrado.py::test_columnas_sensibles_cifradas` (no nulos y sin el texto en claro) y `::test_ninguna_columna_de_contacto_fuera_del_catalogo` (con el sabotaje `leads.telefono text`).
- [ ] T026 [Paso 4] **Verde:** `repositorio_leads.py` cifra `telefono` y `email` con AAD de su columna, calcula `telefono_hmac` y descifra al leer (nombre y dirección ya los cifra T056e).
- [ ] T027 [Paso 4] **Advisor** revisa T023 y T025 (más T021 si P2 ya lo trajo).
- [ ] T039p [Paso 7] **Rojo:** `::test_telefono_invalido_queda_nulo`, `::test_web_en_host_compartido_no_se_guarda` (necesita T006/T007), `::test_web_wa_me_pasa_a_telefono`; la fixture suma `phone` inválido, `wa.me` y host compartido.
- [ ] T040p [Paso 7] **Verde:** `EmpresaCruda` suma `telefono`, `email`, `telefono_canal`, `email_canal` con default (enmienda §Puertos); mapeo con `a_e164` y `normalizar_dominio`; `wa.me` a `telefono` con `whatsapp_osm`, nunca en `web`.
- [ ] T050 [Paso 9] **Rojo:** `test_cifrado.py::test_contacto_no_aparece_en_logs` y `::test_contacto_no_queda_en_claro_en_columnas_no_catalogadas`, cada uno con su sabotaje con nombre.

### P2: normalización y dedup (Pasos 1, 4, 5, 6 y 9)

- [ ] T004 [Paso 1] **Rojo:** `test_normaliza_nombre`, `test_normaliza_ciudad`.
- [ ] T005 [Paso 1] **Verde:** `normalizar_nombre`, `normalizar_ciudad` en `dominio/normalizacion.py`.
- [ ] T006 [Paso 1] **Rojo:** `test_normaliza_dominio`, `test_dedup_yaml_real_carga_hosts_compartidos`, `test_dominio_compartido_no_sirve_para_dedup`.
- [ ] T007 [Paso 1] **Verde:** `normalizar_dominio`, `backend/config/dedup.yaml`, `cargar_hosts_compartidos`. El constructor de OSM suma `hosts_compartidos`.
- [ ] T010 [Paso 1] **Rojo:** `test_distancia_en_metros`.
- [ ] T011 [Paso 1] **Verde:** `dominio/geo.py` (haversine).
- [ ] T019 [Paso 4] **Rojo:** `test_pg_trgm_en_extensions_y_usable_por_app_rt`.
- [ ] T020 [Paso 4] **Verde:** `CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions` en la `0003` y el GIN sobre `nombre_normalizado`.
- [ ] T021a [Paso 4] **Preparación:** `revision_dedup` sin RLS (con `GRANT` a `app_rt`, `CHECK (lead_a < lead_b)` y `UNIQUE`). Se suma a `TABLAS` de `test_rls.py` (002 T017 lo pide).
- [ ] T021 [Paso 4] **Rojo:** `test_rls.py::test_tenant_b_no_accede_a_datos_de_a[revision_dedup]`.
- [ ] T022 [Paso 4] **Verde:** `ENABLE`/`FORCE ROW LEVEL SECURITY` y la policy.
- [ ] T028 [Paso 5] **Rojo:** las reglas 1–3, el veto y el desempate (tests de la versión anterior).
- [ ] T029 [Paso 5] **Rojo:** la regla 4 con geo y bordes.
- [ ] T030 [Paso 5] **Rojo:** aplicar el resultado (revisión, completar nulos, canal y `tipo_titular` solo suben, `cumplimiento` intacto).
- [ ] T031 [Paso 5] **Advisor** revisa T028–T030.
- [ ] T032 [Paso 5] **Verde:** `clasificar_similitud` y umbrales.
- [ ] T033 [Paso 5] **Verde:** `resolver_duplicado`.
- [ ] T034 [Paso 5] **Verde:** `Geo`, `Lead`, `CambiosLead`, `fusionar` y su aplicación contra el puerto.
- [ ] T035 [Paso 6] **Rojo:** `test_dedup_repo.py` contra `pg_trgm` real, incluido `test_aplicar_fusion_simple_no_pisa_y_par_que_sube_reemplaza`.
- [ ] T036 [Paso 6] **Verde:** consultas de dedup y `aplicar_fusion` en `repositorio_leads.py`, con el sabotaje `coalesce` sobre el par.
- [ ] T035b [Paso 6] **Rojo** (advisor antes del verde): `test_dedup_repo.py::test_candidatos_por_nombre_incluye_no_juridicas_descifrando`, `::test_candidatos_por_ciudad_filtra_tenant_y_cuenta_truncados` (conexión sin RLS; sabotaje: quitar `tenant_id = :t`), `::test_fusion_que_sube_a_juridica_pasa_nombre_y_direccion_a_claro` y `::test_similitud_python_coincide_con_pg_trgm`; `test_busqueda_dos_fuentes.py::test_osm_primero_y_supersociedades_despues_fusiona_con_nombre_cifrado`; unitario `test_normalizacion.py::test_similitud_trigramas` (idénticos 1.0, plural largo ≥ 0,92, plural corto en [0,85; 0,92), distintos < 0,85). Sabotajes con nombre: `solo_pg_trgm` (la regla 4 ignora los cifrados → el test de orden OSM-primero falla), `fusion_sin_pasar_a_claro` (viola el `CHECK`). — T056e
- [ ] T036b [Paso 6] **Verde:** `similitud_trigramas` en `dominio/normalizacion.py`; `candidatos_por_nombre` une `pg_trgm` (jurídicos) y descifrado por ciudad (no jurídicos) con `tenant_id = :t` explícito, `ORDER BY creado_en` y tope 2000 con conteo de truncados; `aplicar_fusion` con las reglas (a)/(b)/(c) de "Nombre y dirección cifrados". La migración de osm_dedup suma `CHECK (tipo_titular = 'juridica' OR nombre_normalizado IS NULL)` (con su rojo en `test_dedup_repo.py`). — T035b, T056 (la `0005` aplicada: con los `CHECK` `NOT VALID`, un `UPDATE` a un lead viejo en claro falla)
- [ ] T049p [Paso 9] **Rojo:** `test_busqueda_dos_fuentes.py` (los 4 tests de la versión anterior, con el assert de `cumplimiento` y el sabotaje de re-lanzar). Espera a Croma (002 T031).
- [ ] T051p [Paso 9] **Verde:** `ejecutar_busqueda` normaliza, llama a `resolver_duplicado` y aplica fusión/revisión/nuevo; resumen con `truncado` y `descartados_sin_nombre`.

### P3: OSM completo (Paso 7)

- [ ] T041p [Paso 7] **Rojo:** `::test_limitador_espera_un_segundo_entre_requests`, `::test_retry_after_tiene_tope_de_diez_segundos`, `::test_segundo_fallo_se_reporta_sin_tragarlo`, `::test_quinientos_elementos_marca_truncado`, y el conteo de `descartados_sin_nombre`. Además, `::test_timeout_tambien_escribe_su_fila`: un `httpx.TimeoutException` deja su fila de `overpass_query` (el `finally` de T044 ya la escribe) y sale como `FuenteNoDisponible`, sin propagar el error de `httpx`.
- [ ] T041q [Paso 7] **Rojo + Verde** (advisor 5a): test del escape del QL en `armar_query`. Una `ciudad` con `"` y con `\` queda como literal escapado y no cierra el string de la query.
- [ ] T015p [Paso 2] (advisor 5d): `seleccion.py` usa `cubre(...)` para el país cuando T016b lo deje solo con el país; si no, se borra el comentario de `seleccion.py:17`.
- [ ] T044p [Paso 7] **Verde:** limitador con reloj y `sleep` inyectables, un reintento ante 429/504, `PaginaEmpresas` con `truncado` y `descartados_sin_nombre` (con default).
- [ ] T052p [Paso 10] Resumen por fuente completo en la CLI (fusionados por regla, en revisión, descartados, truncado, "0 elementos: revisar `--ciudad`").

### P4: Croma (después de 002 T030/T031)

- [ ] T045 [P] [Paso 7] **Rojo:** `test_croma_supersociedades.py::test_mapea_geo` y `::test_registro_no_trae_canal_publicado` (con sabotaje). — 002: T030
- [ ] T046 [Paso 7] **Verde:** `croma_supersociedades.py` mapea `geo` y deja los canales en `None`.
- [ ] T047p [Paso 8] **Rojo:** `test_carga_config_fuentes_yaml_real_sin_error` pasa a esperar `sin_implementacion == {"croma_dian_trade_co"}`, después de que 002 T031 le saque el `xfail`. — 002: T031

### P5: doc

- [ ] T054 [P] [Paso 11] `docs/arquitectura-backend.md`: adaptador OSM, selección y `actividades.yaml` en cuanto cierra el [MIN]. Normalización, dedup y cifrado cuando llegan P1 y P2.

---

## Dependencias

- **[MIN] que arranca ya** (depende solo de 002 T001–T019, hechas): T012 → T013; T014 → T015; T037 → T038 → T039 → T040 → T041 → T043 → T044; T047 → T048 (inmediatamente después de T038, por la ventana de rojo de 002 T036).
- **[MIN] que espera a la 002:**
  - T042 espera 002 T024 y T025, y entra en la revisión de T043.
  - T049 espera 002 T021, T025 y T039, y va antes de T016a/T016b.
  - T016a y T016b esperan 002 T038 y T039.
  - T051 va después de T016b.
  - T048b espera 002 T034 y T035, o que se adelanten con OSM (ver la dudosa de la Fase 4).
  - T052 espera 002 T040 y T041.
  - En `main`, 002 T038 depende de T021 **y de T031 (Croma)**, así que T016a/b, T049, T051, T052 y T053 esperan a Croma de forma indirecta. Esto cambia si la 002 reordena para que su caso de uso no espere a Croma.
  - T053 va después de T052.
  - T055 cierra.
- **Dónde se pueden pisar con la 002:**
  - `adaptadores/__init__.py` (T048 y 002 T031): una línea, se dejan las dos claves.
  - `cubre()` y `ejecutar_busqueda.py` (T016a/b y 002 T038/T039): por eso T016a/b esperan.
  - `test_costos_repo.py` (T042 y 002 T024/T026/T032): T042 suma un test al archivo de la 002, no lo crea.
  - `test_cli.py` (T052 y 002 T040): T052 suma un test.
- **Pulido:**
  - P1 entra entero (menos lo que ya subió a la Fase 6b), y T040p necesita T007 de P2 para el host compartido.
  - Fase 6b: T056a → T056b (DDL aprobado 2026-10-18) → T056c → T056d (advisor) → T056e → T056f → T056g; T056e2 (`hide_parameters`) antes de T056f; T056 al final. **Orden obligatorio:** `0003` → (el dueño borra a mano los leads de prueba en claro, si hay) → `0005` (T056) → recién ahí `aplicar_fusion` (T036/T036b). T035b/T036b esperan T056e, T056 y la regla 4 de P2.
  - En P2, T021a–T022, T019–T020 y T023a (P1) van en la misma `0003`: una migración en el PR de Pulido.
  - T049p y P4 esperan a Croma (002 T030/T031).

## Estrategia

1. **[MIN] primero:** login → Nueva búsqueda → OSM devuelve leads → se guardan por tenant → se ven en el tablero. Las tareas "ya" se hacen en paralelo con la 002; las que esperan, en cuanto la 002 pone sus IDs en verde. Login, endpoint y tablero son de otras slices: lo que esta deja es `EjecutarBusqueda` con OSM, probado por tenant (T049), y la CLI (T052).
2. **Pulido después**, en el orden P1 → P2 → P3 → P4 → P5. P1 primero porque sin contacto Dapta no califica, y el contacto no entra sin cifrado. P2 inmediatamente después, porque hasta entonces las búsquedas repetidas duplican leads de OSM.
3. Si el tiempo no alcanza dentro de Pulido, se corta en este orden: T054 (deuda en el PR), T052p (fusionados en total), los pares de plural de T035, y el limitador de T041p (`sleep(1)` fijo con `# ponytail:`). P1 no se corta a medias: entra entero o el contacto sigue sin guardarse.
