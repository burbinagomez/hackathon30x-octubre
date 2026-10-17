# Tasks: 003 — OSM Overpass, normalización común y dedup en 4 niveles

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Prerequisites**: slice 002 mergeado en `main`. Las preguntas P1–P11 están cerradas en `plan.md` (sección Preguntas abiertas), contra el plan 002 en `89d3e59` y las enmiendas de la spec 003 §Puertos.

> Formato de `/speckit-tasks` aplicado a mano (`setup-plan.sh` no resuelve el feature).

**Formato**: `- [ ] TNNN [P?] [Paso] Descripción`
- **[P]**: se puede hacer en paralelo (otro archivo, sin dependencia con una tarea abierta).
- **[Paso n]**: el paso del "Plan de tareas" de la spec.
- Cada **Rojo** se corre y se ve fallar **por la razón correcta** (aserción, no `ImportError` de un archivo que falta) antes de su **Verde**. Un test que nace verde no se acepta: se rompe a propósito la implementación para verlo fallar.

Comando de la suite: `cd backend && uv run pytest -q && uv run lint-imports`.

---

## Fase 1: Setup

- [ ] T001 Puerta: 002 mergeado en `main` y esta rama al día con `main`. Sin esto no arranca ninguna tarea que toque el código del 002.
- [ ] T002 [P] `phonenumbers` y `cryptography` en `backend/pyproject.toml` + `uv.lock`; `pip-audit` limpio.
- [ ] T003 [P] Contrato de import-linter en `backend/pyproject.toml`: `phonenumbers` permitida en `descubrimiento.dominio`; `cryptography` y `httpx` siguen fuera del dominio. `uv run lint-imports` verde.

**Checkpoint**: deps instaladas, lint-imports verde.

---

## Fase 2: Normalización y geo (Paso 1) — sin bloqueo

Fases 2, 3 y 4 son independientes entre sí: se pueden hacer en paralelo.

- [ ] T004 [Paso 1] **Rojo:** `backend/tests/unit/descubrimiento/test_normalizacion.py::test_normaliza_nombre` y `::test_normaliza_ciudad` (casos de la spec).
- [ ] T005 [Paso 1] **Verde:** `normalizar_nombre`, `normalizar_ciudad` en `backend/app/modulos/descubrimiento/dominio/normalizacion.py` (NFKD, lista cerrada de sufijos).
- [ ] T006 [Paso 1] **Rojo:** `::test_normaliza_dominio`, `::test_dedup_yaml_real_carga_hosts_compartidos`, `::test_dominio_compartido_no_sirve_para_dedup` (incluye `tiendafacebook.com` como control de sufijo de host).
- [ ] T007 [Paso 1] **Verde:** `normalizar_dominio(url, hosts_compartidos: frozenset)`; `backend/config/dedup.yaml` con la lista de la spec; `cargar_hosts_compartidos` en `aplicacion/registro.py`, junto a `cargar_registro` (002 plan:257).
- [ ] T008 [Paso 1] **Rojo:** `::test_telefono_a_e164`, `::test_mismo_numero_con_y_sin_indicativo_da_el_mismo_e164`.
- [ ] T009 [Paso 1] **Verde:** `a_e164(valor, region)` con `phonenumbers.parse` + `is_valid_number`.
- [ ] T010 [Paso 1] **Rojo:** `::test_distancia_en_metros`.
- [ ] T011 [Paso 1] **Verde:** `backend/app/modulos/descubrimiento/dominio/geo.py` (haversine, `math`).

**Checkpoint**: `test_normalizacion.py` verde.

---

## Fase 3: Selección de fuentes (Paso 2)

- [ ] T012 [P] [Paso 2] **Rojo:** `backend/tests/unit/descubrimiento/test_seleccion_fuentes.py::test_actividades_yaml_real_carga_y_mapea_4711`.
- [ ] T013 [Paso 2] **Verde:** `backend/config/actividades.yaml` (4711, 5611, 4752, contenido de la spec) + `cargar_actividades` en `aplicacion/registro.py`.
- [ ] T014 [Paso 2] **Rojo:** `::test_icp_colombia_completo_usa_las_dos_fuentes`, `::test_icp_sin_ciudad_ignora_osm_por_geografia`, `::test_ciiu_sin_mapeo_ignora_osm`, `::test_icp_fuera_de_colombia_solo_usa_osm[BR|PE]` (parametrizado; con las `MetaFuente` del `fuentes.yaml` real: `seleccionadas.keys() == {"osm_overpass"}` e `ignoradas == {"croma_supersociedades_co": "pais"}`) y `::test_criterio_no_declarado_no_llega_al_adaptador`.
- [ ] T015 [Paso 2] **Verde:** `seleccionar_fuentes(metas: Iterable[MetaFuente], criterios, actividades) -> tuple[dict[str, CriteriosICP], dict[str, str]]` (`seleccionadas`, `ignoradas`) en `dominio/seleccion.py`. Recibe `MetaFuente`, no `Registro` (tipo de `aplicacion`; contrato `layers`, 002 plan:31). País con `cubre()` → actividad → geografía. Por fuente, `CriteriosICP.filtros` queda reducido a las claves que declara (criterio presente = clave del mapeo, nunca clave con `None`; `ciiu` → `tipo_negocio` como `tuple` de etiquetas OSM). Motivos `pais`, `sin_mapeo_actividad`, `sin_geografia`.
- [ ] T016a [Paso 2] **Rojo (test del 002 que se actualiza):** `backend/tests/unit/descubrimiento/test_dominio.py::test_cubre`, el caso "falso con un filtro fuera de `meta.filtros`" pasa a esperar **verdadero** (falla por assert con el `cubre()` estricto del 002).
- [ ] T016b [Paso 2] **Verde:** `cubre()` queda solo con el país (se saca `set(filtros) ⊆ meta.filtros`); `EjecutarBusqueda` le pasa `[m for _, m in registro.fuentes]` a `seleccionar_fuentes`, deja de usar el `cubre()` estricto y deriva `sin_fuente_para` de `seleccionadas` vacío. `test_sin_fuente_para_el_pais_se_reporta` (002) se corre y sigue verde; si la derivación está mal, falla ahí.

**Checkpoint**: `test_seleccion_fuentes.py`, `test_cubre` actualizado y el resto de la suite del 002 verdes.

---

## Fase 4: Cifrador (Paso 3) — sin bloqueo

- [ ] T017 [P] [Paso 3] **Rojo:** `backend/tests/unit/seguridad/test_cifrador.py`: `::test_ida_y_vuelta`, `::test_mismo_texto_da_cifrado_distinto`, `::test_aad_de_otra_columna_no_descifra`, `::test_hmac_es_determinista_y_distinto_de_la_clave_de_cifrado`, `::test_mismo_numero_con_y_sin_indicativo_da_el_mismo_hmac` (depende de T009), `::test_falla_sin_cifrado_key`. La clave de prueba se genera en el test; nunca un literal que parezca real.
- [ ] T018 [Paso 3] **Verde:** `backend/app/seguridad/cifrado.py` (`Cifrador`: AES-256-GCM, nonce de 12 bytes como prefijo, AAD `tabla.columna`; dos subclaves HKDF-SHA256; `hmac_telefono`), `backend/app/seguridad/catalogo_sensibles.py` (`leads.telefono_cifrado`, `leads.email_cifrado`), `cifrado_key` en `Settings` y `ConfigInvalida` en `backend/app/config.py` al crear la app.

**Checkpoint**: `test_cifrador.py` verde; la app no arranca sin `CIFRADO_KEY`.

---

## Fase 5: Migración `0003` (Paso 4)

- [ ] T019 [Paso 4] **Rojo:** `backend/tests/arquitectura/test_migraciones.py::test_pg_trgm_en_extensions_y_usable_por_app_rt` sobre `base_vacia` (falla: `similarity()` no existe).
- [ ] T020 [Paso 4] **Verde:** `supabase/migrations/0003_osm_dedup.sql`, a mano, arranca con `CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions`.
Regla del 002 (002 plan:32): si el rojo natural es `UndefinedTable`/`UndefinedColumn`, primero se crea el objeto sin la protección y el rojo sale de un assert; recién después va la protección.

- [ ] T021a [Paso 4] **Preparación:** `revision_dedup` en la `0003` con sus columnas, `GRANT` a `app_rt`, `CHECK (lead_a < lead_b)` y `UNIQUE (lead_a, lead_b)`, **sin** RLS ni policy.
- [ ] T021 [Paso 4] **Rojo:** `backend/tests/integration/test_rls.py::test_tenant_b_no_accede_a_datos_de_a[revision_dedup]` (se suma al parametrizado del 002). Falla por assert: B ve las filas de A.
- [ ] T022 [Paso 4] **Verde:** `ENABLE`/`FORCE ROW LEVEL SECURITY` y policy por `app.tenant_id` como el resto.
- [ ] T023a [Paso 4] **Preparación:** columnas nuevas de `leads` en la `0003` **sin** `CHECK`; GIN `extensions.gin_trgm_ops` sobre `nombre_normalizado`; btree no únicos `(tenant_id, dominio)` y `(tenant_id, telefono_hmac)`. La `0003` no toca `costos`: el `CHECK` de `costos.tipo` ya incluye `overpass_query` (002 plan:210).
- [ ] T023 [Paso 4] **Rojo:** `backend/tests/integration/test_dedup_repo.py::test_canal_null_si_y_solo_si_dato_null` y `::test_check_de_canales` (INSERT crudo). Fallan por assert: el INSERT inválido no lanza `CheckViolation`.
- [ ] T024 [Paso 4] **Verde:** los `CHECK` de canal y de dato ⇔ canal en la `0003`.
- [ ] T025 [Paso 4] **Rojo:** `backend/tests/arquitectura/test_cifrado.py`:
  - `::test_columnas_sensibles_cifradas`: escribe vía `obtener_o_crear_lead` con `telefono`/`email` en la `EmpresaCruda` y afirma que `telefono_cifrado`/`email_cifrado` **no son nulos** y no contienen el texto en claro (sin el primer assert, un repo que no guarda nada pasa). Nace rojo porque el repo del 002 no escribe esas columnas.
  - `::test_ninguna_columna_de_contacto_fuera_del_catalogo` (lista cerrada `leads.telefono_canal`, `leads.email_canal`, `leads.idioma_contacto`, `fuente_cache.respuesta`; las dos últimas son de la `0002`, 002 plan:211). Nace verde, así que se ve fallar con un **sabotaje con nombre**: una columna temporal `leads.telefono text` en la base de test → rojo nombrando `leads.telefono`; se quita el sabotaje y vuelve a verde.
- [ ] T026 [Paso 4] **Verde:** `repositorio_leads.py` cifra `telefono`/`email` con AAD de su columna, calcula `telefono_hmac` al escribir y descifra al leer.
- [ ] T027 [Paso 4] **Advisor** revisa T021, T023 y T025 (RLS, `CHECK` y cifrado) antes de aceptarlos. Correcciones antes de seguir.

**Checkpoint**: `migrar_local.sh` dos veces desde vacío sin drift; RLS, `CHECK` y catálogo verdes.

---

## Fase 6: Dedup en dominio (Paso 5)

Los tres Rojo van en `backend/tests/unit/descubrimiento/test_dedup.py` con repositorio falso (implementa `por_id_fiscal`, `por_dominio`, `por_telefono`, `candidatos_por_nombre`, `registrar_revision` y `aplicar_fusion` sobre `Lead` en memoria); se escriben juntos y se revisan antes del primer Verde.

- [ ] T028 [Paso 5] **Rojo (reglas 1–3, veto, desempate):** `::test_regla_1_mismo_id_fiscal_fusiona`, `::test_regla_2_mismo_dominio_fusiona`, `::test_regla_3_mismo_telefono_fusiona`, `::test_host_compartido_no_fusiona_por_regla_2` (con su control), `::test_dominio_gana_sobre_telefono`, `::test_id_fiscal_distinto_nunca_fusiona`, `::test_veto_excluye_candidato_y_sigue_con_la_regla_siguiente`, `::test_veto_sigue_con_el_siguiente_candidato_de_la_misma_regla`, `::test_desempate_por_creado_en` (parametrizado con los dos órdenes del repo falso: un "toma el primero" falla en uno).
- [ ] T029 [Paso 5] **Rojo (regla 4):** `::test_regla_4_nombre_similar_misma_ciudad_fusiona`, `::test_homonimo_cercano_fusiona`, `::test_homonimo_lejano_va_a_revision`, `::test_homonimo_sin_geo_va_a_revision`, `::test_borde_de_distancia`, `::test_homonimos_osm_lejanos_van_a_revision`, `::test_regla_4_prefiere_candidato_fusionable_sobre_revision`, `::test_regla_4_ordena_por_similitud_y_despues_creado_en` (parametrizado con los dos órdenes del repo falso), `::test_sin_ciudad_salta_regla_4`, `::test_misma_ciudad_es_requisito_de_regla_4`, `::test_bordes_de_similitud`.
- [ ] T030 [Paso 5] **Rojo (aplicar el resultado):** `::test_revision_inserta_lead_nuevo_y_fila_pendiente`, `::test_fusion_completa_nulos_sin_pisar` (con el caso cruzado dato/canal), `::test_canal_sube_y_nunca_baja`, `::test_tipo_titular_sube_y_nunca_baja`, `::test_fusion_no_toca_cumplimiento` (solo contra el repo falso; el SQL real lo prueba T049, `test_supersociedades_y_osm_dan_un_lead`).
- [ ] T031 [Paso 5] **Advisor** revisa T028–T030 (dedup difuso, veto, geo, par dato+canal) antes de implementar.
- [ ] T032 [Paso 5] **Verde:** `clasificar_similitud`, `UMBRAL_FUSION = 0.92`, `UMBRAL_REVISION = 0.85`, `DISTANCIA_MAX_FUSION_M = 250` en `dominio/dedup.py`.
- [ ] T033 [Paso 5] **Verde:** `resolver_duplicado`: reglas 1 → 4 en orden, veto por `id_fiscal` distinto que excluye y sigue, desempate en dominio; regla 4 recorre por similitud desc y `creado_en` asc buscando el primer fusionable antes de caer a revisión.
- [ ] T034 [Paso 5] **Verde:** `Geo`, `Lead` y `CambiosLead` en `dominio/modelos.py`; `fusionar(lead, empresa) -> CambiosLead` pura (nulos a completar, par dato+canal por confianza `whatsapp_comercial` > `sitio_web` > `osm_contacto` > `whatsapp_osm`, empate → el que estaba; `tipo_titular` solo sube) y su aplicación contra el puerto: `aplicar_fusion(lead.id, cambios)` + `agregar_lead_fuente` del 002; `cumplimiento` intacto; revisión = `obtener_o_crear_lead` + `registrar_revision`.

**Checkpoint**: `test_dedup.py` verde.

---

## Fase 7: Repositorio contra `pg_trgm` real (Paso 6)

- [ ] T035 [Paso 6] **Rojo:** `backend/tests/integration/test_dedup_repo.py`: `::test_nombre_identico_tras_normalizar_es_candidato_de_fusion`, `::test_plural_largo_cae_en_fusion`, `::test_plural_corto_cae_en_revision`, `::test_nombres_distintos_no_son_candidatos`, `::test_mismo_nombre_otra_ciudad_no_es_candidato`, `::test_por_telefono_encuentra_por_hmac`, `::test_por_dominio_devuelve_todos_los_que_coinciden`, `::test_par_de_revision_no_se_duplica_invertido`, y `::test_aplicar_fusion_simple_no_pisa_y_par_que_sube_reemplaza` (dos casos: un campo simple ya lleno no cambia; el par `whatsapp_osm` se reemplaza por `osm_contacto` junto con `telefono_hmac`). Para que el rojo salga de un assert, se arranca con un `aplicar_fusion` de `UPDATE` plano, sin `coalesce`: falla el caso simple. Si Postgres real ubica un par fuera de su banda, se cambia el par, no el umbral.
- [ ] T036 [Paso 6] **Verde:** `por_id_fiscal`, `por_dominio`, `por_telefono` (por HMAC), `aplicar_fusion` (`coalesce` en los simples; el par que trae `CambiosLead` se reemplaza completo, cifrado + hmac + canal, sin `coalesce`: con `coalesce` sobre el par falla el caso del par que sube), `candidatos_por_nombre` (`similarity() >= UMBRAL_REVISION`, ciudad por igualdad), `registrar_revision` (ordena el par, `ON CONFLICT DO NOTHING`) en `repositorio_leads.py`. Sin archivos nuevos en `persistencia/`.

**Checkpoint**: `test_dedup_repo.py` verde.

---

## Fase 8: Adaptador OSM (Paso 7)

Desde T038, `osm_overpass.py` existe en `infraestructura/adaptadores/` y los tests de arquitectura del 002 la recorren: `test_costos_por_adaptador.py::test_todo_adaptador_de_registro_recibe_registro_costos` la cubre desde que nace (el constructor recibe `RegistroCostos`), y `test_registro_adaptadores.py::test_todo_adaptador_de_registro_esta_declarado` queda **en rojo hasta T048** (la clase existe y todavía no está en el catálogo). Es un rojo esperado: no se tapa ni se saltea. Durante la Fase 8 es el **único** rojo permitido fuera del test de la tarea en curso; la revisión de T043 y el checkpoint corren con esa excepción.

- [ ] T037 [Paso 7] **Rojo:** `backend/tests/fixtures/osm/` (respuestas sintéticas: nodo, `way` con `center`, sin `name`, `phone` inválido, `wa.me`, host compartido, 500 y 499 elementos; teléfonos CO válidos para `phonenumbers`) y `backend/tests/unit/descubrimiento/test_osm_overpass.py::test_query_acotada_con_timeout_y_tope`, `::test_envia_user_agent_identificable`.
- [ ] T038 [Paso 7] **Verde:** `infraestructura/adaptadores/osm_overpass.py` con el constructor del 002 (`meta`, `RegistroCostos`, transporte, `costo_unitario`, `lote_id`; 002 plan:150) más `hosts_compartidos`, reloj, `sleep` y `url`; valida criterios contra `meta.filtros` antes de cualquier request; query única, URL por constante con override `overpass_url` de `Settings`, User-Agent `dapta-reto-30x/<versión>` con la URL del repo desde config, `httpx` con timeout de 30 s.
- [ ] T039 [Paso 7] **Rojo:** `::test_mapea_elemento_a_empresa_cruda` (incluye `adaptador.meta.licencia == "ODbL"` y `geo`), `::test_elemento_sin_nombre_se_descarta_y_se_cuenta`, `::test_telefono_invalido_queda_nulo`, `::test_web_en_host_compartido_no_se_guarda`, `::test_web_wa_me_pasa_a_telefono`, `::test_quinientos_elementos_marca_truncado`.
- [ ] T040 [Paso 7] **Verde:** mapeo a `EmpresaCruda` con `normalizar_dominio` y `a_e164` del dominio; `telefono_canal`/`email_canal`; `wa.me` a `telefono` con `whatsapp_osm` solo sin otro válido, nunca en `web`; `PaginaEmpresas(empresas, total=None, truncado, descartados_sin_nombre)`; los dos campos nuevos van con default en `dominio/modelos.py` (enmienda de la spec 003 §Puertos), así Croma no cambia.
- [ ] T041 [Paso 7] **Rojo:** `::test_limitador_espera_un_segundo_entre_requests`, `::test_registra_segundos_de_cada_intento`, `::test_retry_after_tiene_tope_de_diez_segundos`, `::test_segundo_fallo_se_reporta_sin_tragarlo`.
- [ ] T042 [Paso 7] **Rojo:** `backend/tests/integration/test_costos_repo.py::test_overpass_query_escribe_fila_en_costos` (`postgres_costos` real, `unidades == Decimal(2)`, `costo_unitario` como `numeric`, `tenant_id` del contexto). Se escribe ahora, antes del Verde de T044, para que nazca rojo.
- [ ] T043 [Paso 7] **Advisor** revisa T041–T042 (costos por intento, sin espera cobrada, `Decimal`) antes de implementar.
- [ ] T044 [Paso 7] **Verde:** limitador con reloj y `sleep` inyectables (`# ponytail:` por proceso); un reintento ante 429/504 (`Retry-After` con tope 10 s; sin él, `max(1, limitador)`); `RegistroCostos.registrar` con `overpass_query` por intento **antes de devolver o lanzar**; `FuenteNoDisponible` sin el cuerpo de la respuesta. La tarifa llega por constructor ya como `Decimal(str(v))` desde la raíz de composición del 002 (002 plan:150); `lote_id = busqueda_id` y `ts` lo pone la base (002 plan:286, :291).
- [ ] T045 [P] [Paso 7] **Rojo:** `backend/tests/unit/descubrimiento/test_croma_supersociedades.py::test_mapea_geo` (la fixture del 002 suma `lat/lon`) y `::test_registro_no_trae_canal_publicado`. Este último nace verde (los campos tienen default `None`): se ve fallar con el sabotaje de que el mapeo ponga `telefono_canal="sitio_web"`, y se quita.
- [ ] T046 [Paso 7] **Verde:** `croma_supersociedades.py` mapea `geo` y deja `telefono_canal`/`email_canal` en `None`.

**Checkpoint**: `test_osm_overpass.py`, `test_croma_supersociedades.py` y `test_costos_repo.py` verdes. El único rojo permitido en la suite es `test_todo_adaptador_de_registro_esta_declarado`, que pasa a verde en T048.

---

## Fase 9: Contrato y registro (Paso 8)

Inversión catálogo → fábrica: la suite de contrato del 002 se parametriza sobre el catálogo (002 plan:155-162), así que el rojo lo da sumar la clave y el verde, la fábrica. `test_fuente_descubrimiento.py` no se toca.

- [ ] T047 [Paso 8] **Rojo:** `backend/tests/unit/descubrimiento/test_registro.py::test_carga_config_fuentes_yaml_real_sin_error` pasa a esperar `sin_implementacion == {"croma_dian_trade_co"}` (falla: `osm_overpass` sigue en `sin_implementacion`).
- [ ] T048 [Paso 8] **Verde:** `osm_overpass` en el catálogo de `infraestructura/adaptadores/__init__.py`. `config/fuentes.yaml` no cambia (la entrada ya está con `habilitado: true`). Pone en verde `test_registro` y `test_todo_adaptador_de_registro_esta_declarado` (rojo desde T038), y en **rojo** `backend/tests/contratos/test_fuente_descubrimiento.py::test_hay_fabrica_para_cada_clave_del_catalogo` (falta la fábrica).
- [ ] T048b [Paso 8] **Verde:** fábrica `osm_overpass` en `backend/tests/contratos/fabricas.py` (`fabrica(transporte, registro)`, con transporte falso sobre la fixture de `tests/fixtures/osm/`). Corren los tres tests de contrato con `[osm_overpass]`; `::test_rechaza_criterio_no_soportado[osm_overpass]` usa la centinela `"__criterio_inexistente__"` del 002 (002 plan:160).

**Checkpoint**: suite de contrato verde para las dos fuentes; `test_registro_adaptadores.py` y `test_costos_por_adaptador.py` verdes.

---

## Fase 10: `EjecutarBusqueda` con dos fuentes (Paso 9)

- [ ] T049 [Paso 9] **Rojo:** `backend/tests/integration/test_busqueda_dos_fuentes.py`: `::test_supersociedades_y_osm_dan_un_lead`, `::test_orden_de_fuentes_no_cambia_el_resultado`, `::test_homonimo_lejano_no_hereda_el_telefono`, `::test_osm_caido_no_pierde_supersociedades`.
  - `test_supersociedades_y_osm_dan_un_lead` suma el assert de que la única fila de `cumplimiento` sigue con `fuente='croma_supersociedades_co'` y la licencia original (contar "1 cumplimiento" no alcanza: prueba el SQL de `aplicar_fusion`).
  - `test_osm_caido_no_pierde_supersociedades` nace verde (el aislamiento es del 002): se ve fallar con el sabotaje de re-lanzar `FuenteNoDisponible` en `EjecutarBusqueda`, y se quita.
- [ ] T050 [Paso 9] **Rojo:** `backend/tests/arquitectura/test_cifrado.py::test_contacto_no_aparece_en_logs` (`caplog` en `DEBUG`, todos los loggers, incluido `httpx`) y `::test_contacto_no_queda_en_claro_en_columnas_no_catalogadas`. Los dos nacen verdes, así que cada uno se ve fallar con su sabotaje y se quita: `logger.debug(e.telefono)` en `EjecutarBusqueda` para el primero; que el mapeo OSM guarde el `wa.me` en `web` para el segundo.
- [ ] T051 [Paso 9] **Verde:** `aplicacion/ejecutar_busqueda.py` normaliza cada `EmpresaCruda`, llama a `resolver_duplicado`, aplica fusión/revisión/nuevo, escribe `cumplimiento` solo para leads nuevos vía `obtener_o_crear_lead(e, meta.licencia)` (OSM: `ODbL`, `url_origen` del elemento, `as_of` de la base OSM, `tipo_titular='desconocido'`), mantiene el aislamiento del 002 de `LimiteFuenteAgotado`/`FuenteNoDisponible` por fuente (002 plan:295) y arma el resumen por fuente con `truncado` y `descartados_sin_nombre` de cada `PaginaEmpresas`. Ningún log con contacto.

**Checkpoint**: suite completa verde.

---

## Fase 11: CLI y corrida real (Paso 10)

- [ ] T052 [Paso 10] `app/cli.py buscar` con `--ciudad` y el resumen por fuente de la spec (encontrados, nuevos, fusionados por regla, en revisión, descartados sin nombre, truncado, ignorados y caídas con motivo; "0 elementos: revisar `--ciudad`"). La spec deja la CLI sin test de formato: lo que la cubre es T049.
- [ ] T053 [Paso 10] **Una** corrida real contra Overpass (Bogotá, 4711), **avisada antes**. Se anotan segundos, elementos, cuántos traen teléfono, el `name` real de la relación de Bogotá, si Croma trae geo y la forma de la respuesta, sin copiar ningún contacto. Si difiere de la fixture: se corrige la fixture y se vuelve a la Fase 8.

---

## Fase 12: Doc y cierre (Paso 11)

- [ ] T054 [P] [Paso 11] `docs/arquitectura-backend.md`: normalización, dedup (4 reglas, veto, geo, cola), cifrado (subclaves, AAD, catálogo), cómo mapear un CIIU nuevo y cómo agregar un host compartido. Primer corte si el tiempo aprieta (deuda en el PR).
- [ ] T055 Cierre: `uv run pytest -q`, `uv run lint-imports`, `scripts/migrar_local.sh` dos veces desde vacío. PR con los cortes aplicados, si los hubo.

---

## Dependencias

- T001 bloquea las fases que tocan código del 002 (3, 5 a 11). T002 bloquea T009 y T018.
- Fases 2, 3 y 4 en paralelo. La Fase 5 necesita T018 (cifrado) para T025–T026.
- Fase 6 necesita Fase 2 (normalización, geo). Fase 7 necesita Fases 5 y 6.
- Fase 8 necesita Fase 2 (mapeo). T042 corre sobre la `0002` (`costos` no cambia). T045–T046 en paralelo con T037–T044.
- Fase 9 inmediatamente después de la Fase 8; durante la Fase 8 el único rojo permitido es `test_todo_adaptador_de_registro_esta_declarado`. Fase 10 necesita Fases 7, 8 y 9. Fase 11 necesita Fase 10.

## Cuándo cortar (de la spec, en este orden)

| Orden | Se corta | Tareas afectadas |
|---|---|---|
| 1 | Doc | T054 (deuda en el PR) |
| 2 | Desglose por regla en la CLI | T052 (fusionados en total) |
| 3 | Pares de plural en integración | `test_plural_largo_cae_en_fusion` y `test_plural_corto_cae_en_revision` de T035 |
| 4 | Limitador con reloj falso | `test_limitador_espera_un_segundo_entre_requests` de T041; `sleep(1)` fijo con `# ponytail:` en T044 |

No se cortan: regla 4 con geo (T029, T033), veto (T028, T033), cifrado (T017–T018, T025–T026), `wa.me` (T039–T040) y logs (T050).
