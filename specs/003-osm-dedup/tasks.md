# Tasks: 003 — OSM Overpass, normalización común y dedup en 4 niveles

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Prerequisites**: slice 002 mergeado en `main`; preguntas abiertas P1–P11 de `plan.md` respondidas.

> Formato de `/speckit-tasks` aplicado a mano (`setup-plan.sh` no resuelve el feature).

**Formato**: `- [ ] TNNN [P?] [Paso] Descripción`
- **[P]**: se puede hacer en paralelo (otro archivo, sin dependencia con una tarea abierta).
- **[Paso n]**: el paso del "Plan de tareas" de la spec.
- Cada **Rojo** se corre y se ve fallar **por la razón correcta** (aserción, no `ImportError` de un archivo que falta) antes de su **Verde**. Un test que nace verde no se acepta: se rompe a propósito la implementación para verlo fallar.
- **Bloqueada por Pn**: no se empieza hasta que la pregunta abierta n del plan esté resuelta.

Comando de la suite: `cd backend && uv run pytest -q && uv run lint-imports`.

---

## Fase 1: Setup

- [ ] T001 Puerta: 002 mergeado en `main`, esta rama rebasada sobre `main`, P1–P11 resueltas y anotadas en `plan.md`. Sin esto no arranca ninguna tarea bloqueada.
- [ ] T002 [P] `phonenumbers` y `cryptography` en `backend/pyproject.toml` + `uv.lock`; `pip-audit` limpio.
- [ ] T003 [P] Contrato de import-linter en `backend/pyproject.toml`: `phonenumbers` permitida en `descubrimiento.dominio`; `cryptography` y `httpx` siguen fuera del dominio. `uv run lint-imports` verde.

**Checkpoint**: deps instaladas, lint-imports verde.

---

## Fase 2: Normalización y geo (Paso 1) — sin bloqueo

Fases 2, 3 y 4 son independientes entre sí: se pueden hacer en paralelo.

- [ ] T004 [Paso 1] **Rojo:** `backend/tests/unit/descubrimiento/test_normalizacion.py::test_normaliza_nombre` y `::test_normaliza_ciudad` (casos de la spec).
- [ ] T005 [Paso 1] **Verde:** `normalizar_nombre`, `normalizar_ciudad` en `backend/app/modulos/descubrimiento/dominio/normalizacion.py` (NFKD, lista cerrada de sufijos).
- [ ] T006 [Paso 1] **Rojo:** `::test_normaliza_dominio`, `::test_dedup_yaml_real_carga_hosts_compartidos`, `::test_dominio_compartido_no_sirve_para_dedup` (incluye `tiendafacebook.com` como control de sufijo de host).
- [ ] T007 [Paso 1] **Verde:** `normalizar_dominio(url, hosts_compartidos: frozenset)`; `backend/config/dedup.yaml` con la lista de la spec; `cargar_hosts_compartidos` en `aplicacion/configuracion.py` (o junto a `cargar_registro` si el 002 ya tiene ese archivo).
- [ ] T008 [Paso 1] **Rojo:** `::test_telefono_a_e164`, `::test_mismo_numero_con_y_sin_indicativo_da_el_mismo_e164`.
- [ ] T009 [Paso 1] **Verde:** `a_e164(valor, region)` con `phonenumbers.parse` + `is_valid_number`.
- [ ] T010 [Paso 1] **Rojo:** `::test_distancia_en_metros`.
- [ ] T011 [Paso 1] **Verde:** `backend/app/modulos/descubrimiento/dominio/geo.py` (haversine, `math`).

**Checkpoint**: `test_normalizacion.py` verde.

---

## Fase 3: Selección de fuentes (Paso 2) — bloqueada por P3, P4, P11

- [ ] T012 [P] [Paso 2] **Rojo:** `backend/tests/unit/descubrimiento/test_seleccion_fuentes.py::test_actividades_yaml_real_carga_y_mapea_4711`.
- [ ] T013 [Paso 2] **Verde:** `backend/config/actividades.yaml` (4711, 5611, 4752, contenido de la spec) + `cargar_actividades` en `aplicacion/`.
- [ ] T014 [Paso 2] **Rojo:** `::test_icp_colombia_completo_usa_las_dos_fuentes`, `::test_icp_sin_ciudad_ignora_osm_por_geografia`, `::test_ciiu_sin_mapeo_ignora_osm`, `::test_icp_brasil_solo_usa_osm`, `::test_criterio_no_declarado_no_llega_al_adaptador`, y **`::test_icp_peru_solo_usa_osm`** (agregado por el plan; con el `fuentes.yaml` real: `pais=PE` + ciudad + CIIU mapeado → solo `osm_overpass`, el resto ignorado por país o deshabilitado).
- [ ] T015 [Paso 2] **Verde:** `seleccionar_fuentes(registro, criterios, actividades)` en `dominio/seleccion.py`: país → actividad → geografía; criterios por fuente filtrados a sus `filtros`; motivos `pais`, `sin_mapeo_actividad`, `sin_geografia`.
- [ ] T016 [Paso 2] **Refactor:** `EjecutarBusqueda` del 002 delega la selección en `seleccionar_fuentes`. `test_sin_fuente_para_el_pais_se_reporta` (002) sigue verde sin tocarlo.

**Checkpoint**: `test_seleccion_fuentes.py` y la suite del 002 verdes.

---

## Fase 4: Cifrador (Paso 3) — sin bloqueo

- [ ] T017 [P] [Paso 3] **Rojo:** `backend/tests/unit/seguridad/test_cifrador.py`: `::test_ida_y_vuelta`, `::test_mismo_texto_da_cifrado_distinto`, `::test_aad_de_otra_columna_no_descifra`, `::test_hmac_es_determinista_y_distinto_de_la_clave_de_cifrado`, `::test_mismo_numero_con_y_sin_indicativo_da_el_mismo_hmac` (depende de T009), `::test_falla_sin_cifrado_key`. La clave de prueba se genera en el test; nunca un literal que parezca real.
- [ ] T018 [Paso 3] **Verde:** `backend/app/seguridad/cifrado.py` (`Cifrador`: AES-256-GCM, nonce de 12 bytes como prefijo, AAD `tabla.columna`; dos subclaves HKDF-SHA256; `hmac_telefono`), `backend/app/seguridad/catalogo_sensibles.py` (`leads.telefono_cifrado`, `leads.email_cifrado`), `cifrado_key` en `Settings` y `ConfigInvalida` en `backend/app/config.py` al crear la app.

**Checkpoint**: `test_cifrador.py` verde; la app no arranca sin `CIFRADO_KEY`.

---

## Fase 5: Migración `0003` (Paso 4) — P9 para `costos.tipo`

- [ ] T019 [Paso 4] **Rojo:** `backend/tests/arquitectura/test_migraciones.py::test_pg_trgm_en_extensions_y_usable_por_app_rt` sobre `base_vacia` (falla: `similarity()` no existe).
- [ ] T020 [Paso 4] **Verde:** `supabase/migrations/0003_osm_dedup.sql`, a mano, arranca con `CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions`.
- [ ] T021 [Paso 4] **Rojo:** `backend/tests/integration/test_rls.py::test_tenant_b_no_accede_a_datos_de_a[revision_dedup]` (se suma al parametrizado del 002).
- [ ] T022 [Paso 4] **Verde:** `revision_dedup` en la `0003`: columnas de la spec, `ENABLE`/`FORCE ROW LEVEL SECURITY`, policy por `app.tenant_id` como el resto, `CHECK (lead_a < lead_b)`, `UNIQUE (lead_a, lead_b)`, `GRANT` a `app_rt`.
- [ ] T023 [Paso 4] **Rojo:** `backend/tests/integration/test_dedup_repo.py::test_canal_null_si_y_solo_si_dato_null` y `::test_check_de_canales` (INSERT crudo; fallan porque las columnas y los `CHECK` no existen).
- [ ] T024 [Paso 4] **Verde:** columnas nuevas de `leads` en la `0003` con los `CHECK` de canal y de dato ⇔ canal; GIN `extensions.gin_trgm_ops` sobre `nombre_normalizado`; btree no únicos `(tenant_id, dominio)` y `(tenant_id, telefono_hmac)`. Si P9 dice que `costos.tipo` tiene `CHECK`, se amplía con `overpass_query` acá.
- [ ] T025 [Paso 4] **Rojo:** `backend/tests/arquitectura/test_cifrado.py::test_columnas_sensibles_cifradas` y `::test_ninguna_columna_de_contacto_fuera_del_catalogo` (lista cerrada `leads.telefono_canal`, `leads.email_canal`). **Bloqueada por P7** (escribe vía repositorio).
- [ ] T026 [Paso 4] **Verde:** `repositorio_leads.py` cifra `telefono`/`email` con AAD de su columna, calcula `telefono_hmac` al escribir y descifra al leer.
- [ ] T027 [Paso 4] **Advisor** revisa T021, T023 y T025 (RLS, `CHECK` y cifrado) antes de aceptarlos. Correcciones antes de seguir.

**Checkpoint**: `migrar_local.sh` dos veces desde vacío sin drift; RLS, `CHECK` y catálogo verdes.

---

## Fase 6: Dedup en dominio (Paso 5) — bloqueada por P7

Los tres Rojo van en `backend/tests/unit/descubrimiento/test_dedup.py` con repositorio falso; se escriben juntos y se revisan antes del primer Verde.

- [ ] T028 [Paso 5] **Rojo (reglas 1–3, veto, desempate):** `::test_regla_1_mismo_id_fiscal_fusiona`, `::test_regla_2_mismo_dominio_fusiona`, `::test_regla_3_mismo_telefono_fusiona`, `::test_host_compartido_no_fusiona_por_regla_2` (con su control), `::test_dominio_gana_sobre_telefono`, `::test_id_fiscal_distinto_nunca_fusiona`, `::test_veto_excluye_candidato_y_sigue_con_la_regla_siguiente`, `::test_veto_sigue_con_el_siguiente_candidato_de_la_misma_regla`, `::test_desempate_por_creado_en`.
- [ ] T029 [Paso 5] **Rojo (regla 4):** `::test_regla_4_nombre_similar_misma_ciudad_fusiona`, `::test_homonimo_cercano_fusiona`, `::test_homonimo_lejano_va_a_revision`, `::test_homonimo_sin_geo_va_a_revision`, `::test_borde_de_distancia`, `::test_homonimos_osm_lejanos_van_a_revision`, `::test_regla_4_prefiere_candidato_fusionable_sobre_revision`, `::test_regla_4_ordena_por_similitud_y_despues_creado_en`, `::test_sin_ciudad_salta_regla_4`, `::test_misma_ciudad_es_requisito_de_regla_4`, `::test_bordes_de_similitud`.
- [ ] T030 [Paso 5] **Rojo (aplicar el resultado):** `::test_revision_inserta_lead_nuevo_y_fila_pendiente`, `::test_fusion_completa_nulos_sin_pisar` (con el caso cruzado dato/canal), `::test_canal_sube_y_nunca_baja`, `::test_tipo_titular_sube_y_nunca_baja`, `::test_fusion_no_toca_cumplimiento`.
- [ ] T031 [Paso 5] **Advisor** revisa T028–T030 (dedup difuso, veto, geo, par dato+canal) antes de implementar.
- [ ] T032 [Paso 5] **Verde:** `clasificar_similitud`, `UMBRAL_FUSION = 0.92`, `UMBRAL_REVISION = 0.85`, `DISTANCIA_MAX_FUSION_M = 250` en `dominio/dedup.py`.
- [ ] T033 [Paso 5] **Verde:** `resolver_duplicado`: reglas 1 → 4 en orden, veto por `id_fiscal` distinto que excluye y sigue, desempate en dominio; regla 4 recorre por similitud desc y `creado_en` asc buscando el primer fusionable antes de caer a revisión.
- [ ] T034 [Paso 5] **Verde:** fusión pura (`coalesce`, par dato+canal por confianza `whatsapp_comercial` > `sitio_web` > `osm_contacto` > `whatsapp_osm`, empate → el que estaba; `tipo_titular` solo sube) y su aplicación contra el puerto (`lead_fuentes` suma, `cumplimiento` intacto; revisión = lead nuevo + `registrar_revision`).

**Checkpoint**: `test_dedup.py` verde.

---

## Fase 7: Repositorio contra `pg_trgm` real (Paso 6) — bloqueada por P7

- [ ] T035 [Paso 6] **Rojo:** `backend/tests/integration/test_dedup_repo.py`: `::test_nombre_identico_tras_normalizar_es_candidato_de_fusion`, `::test_plural_largo_cae_en_fusion`, `::test_plural_corto_cae_en_revision`, `::test_nombres_distintos_no_son_candidatos`, `::test_mismo_nombre_otra_ciudad_no_es_candidato`, `::test_por_telefono_encuentra_por_hmac`, `::test_por_dominio_devuelve_todos_los_que_coinciden`, `::test_par_de_revision_no_se_duplica_invertido`. Si Postgres real ubica un par fuera de su banda, se cambia el par, no el umbral.
- [ ] T036 [Paso 6] **Verde:** `por_dominio`, `por_telefono` (por HMAC), `candidatos_por_nombre` (`similarity() >= UMBRAL_REVISION`, ciudad por igualdad), `registrar_revision` (ordena el par, `ON CONFLICT DO NOTHING`) en `repositorio_leads.py`. Sin archivos nuevos en `persistencia/`.

**Checkpoint**: `test_dedup_repo.py` verde.

---

## Fase 8: Adaptador OSM (Paso 7) — bloqueada por P1, P2, P5, P6, P8, P10

- [ ] T037 [Paso 7] **Rojo:** `backend/tests/fixtures/osm/` (respuestas sintéticas: nodo, `way` con `center`, sin `name`, `phone` inválido, `wa.me`, host compartido, 500 y 499 elementos; teléfonos CO válidos para `phonenumbers`) y `backend/tests/unit/descubrimiento/test_osm_overpass.py::test_query_acotada_con_timeout_y_tope`, `::test_envia_user_agent_identificable`.
- [ ] T038 [Paso 7] **Verde:** `infraestructura/adaptadores/osm_overpass.py`: query única, URL por constante con override `overpass_url` de `Settings`, User-Agent `dapta-reto-30x/<versión>` con la URL del repo desde config, `httpx` con timeout de 30 s.
- [ ] T039 [Paso 7] **Rojo:** `::test_mapea_elemento_a_empresa_cruda`, `::test_elemento_sin_nombre_se_descarta_y_se_cuenta`, `::test_telefono_invalido_queda_nulo`, `::test_web_en_host_compartido_no_se_guarda`, `::test_web_wa_me_pasa_a_telefono`, `::test_quinientos_elementos_marca_truncado`.
- [ ] T040 [Paso 7] **Verde:** mapeo a `EmpresaCruda` con `normalizar_dominio` y `a_e164` del dominio; `telefono_canal`/`email_canal`; `wa.me` a `telefono` con `whatsapp_osm` solo sin otro válido, nunca en `web`; `truncado` y `descartados_sin_nombre` (forma según P1).
- [ ] T041 [Paso 7] **Rojo:** `::test_limitador_espera_un_segundo_entre_requests`, `::test_registra_segundos_de_cada_intento`, `::test_retry_after_tiene_tope_de_diez_segundos`, `::test_segundo_fallo_se_reporta_sin_tragarlo`.
- [ ] T042 [Paso 7] **Rojo:** `backend/tests/integration/test_costos_repo.py::test_overpass_query_escribe_fila_en_costos` (`postgres_costos` real, `unidades == Decimal(2)`, `costo_unitario` como `numeric`, `tenant_id` del contexto). Se escribe ahora, antes del Verde de T044, para que nazca rojo.
- [ ] T043 [Paso 7] **Advisor** revisa T041–T042 (costos por intento, sin espera cobrada, `Decimal`) antes de implementar.
- [ ] T044 [Paso 7] **Verde:** limitador con reloj y `sleep` inyectables (`# ponytail:` por proceso); un reintento ante 429/504 (`Retry-After` con tope 10 s; sin él, `max(1, limitador)`); `RegistroCostos.registrar` con `overpass_query` por intento **antes de devolver o lanzar**; `FuenteNoDisponible` sin el cuerpo de la respuesta; cargador de tarifas con `Decimal(str(v))` si P10 lo pide.
- [ ] T045 [P] [Paso 7] **Rojo:** `backend/tests/unit/descubrimiento/test_croma_supersociedades.py::test_mapea_geo` (la fixture del 002 suma `lat/lon`) y `::test_registro_no_trae_canal_publicado`.
- [ ] T046 [Paso 7] **Verde:** `croma_supersociedades.py` mapea `geo` y deja `telefono_canal`/`email_canal` en `None`.

**Checkpoint**: `test_osm_overpass.py`, `test_croma_supersociedades.py` y `test_costos_repo.py` verdes.

---

## Fase 9: Contrato y registro (Paso 8) — bloqueada por P5

- [ ] T047 [Paso 8] **Rojo:** `backend/tests/contratos/test_fuente_descubrimiento.py` con el parámetro `[osm_overpass]` y transporte falso (solo el parámetro y, según P5, su fábrica de prueba; los tres tests no se tocan); `backend/tests/unit/descubrimiento/test_registro.py::test_carga_config_fuentes_yaml_real_sin_error` a `sin_implementacion == {"croma_dian_trade_co"}` con `osm_overpass` en el catálogo.
- [ ] T048 [Paso 8] **Verde:** `osm_overpass` en el catálogo de `infraestructura/adaptadores/__init__.py`. `config/fuentes.yaml` no cambia (la entrada ya está con `habilitado: true`).

**Checkpoint**: suite de contrato verde para las dos fuentes.

---

## Fase 10: `EjecutarBusqueda` con dos fuentes (Paso 9) — bloqueada por P1, P7, P8

- [ ] T049 [Paso 9] **Rojo:** `backend/tests/integration/test_busqueda_dos_fuentes.py`: `::test_supersociedades_y_osm_dan_un_lead`, `::test_orden_de_fuentes_no_cambia_el_resultado`, `::test_homonimo_lejano_no_hereda_el_telefono`, `::test_osm_caido_no_pierde_supersociedades`.
- [ ] T050 [Paso 9] **Rojo:** `backend/tests/arquitectura/test_cifrado.py::test_contacto_no_aparece_en_logs` (`caplog` en `DEBUG`, todos los loggers, incluido `httpx`) y `::test_contacto_no_queda_en_claro_en_columnas_no_catalogadas`.
- [ ] T051 [Paso 9] **Verde:** `aplicacion/ejecutar_busqueda.py` normaliza cada `EmpresaCruda`, llama a `resolver_duplicado`, aplica fusión/revisión/nuevo, escribe `cumplimiento` solo para leads nuevos (OSM: `ODbL`, `url_origen` del elemento, `as_of` de la base OSM, `tipo_titular='desconocido'`), aísla `FuenteNoDisponible` por fuente y arma el resumen por fuente. Ningún log con contacto.

**Checkpoint**: suite completa verde.

---

## Fase 11: CLI y corrida real (Paso 10) — bloqueada por P1

- [ ] T052 [Paso 10] `app/cli.py buscar` con `--ciudad` y el resumen por fuente de la spec (encontrados, nuevos, fusionados por regla, en revisión, descartados sin nombre, truncado, ignorados y caídas con motivo; "0 elementos: revisar `--ciudad`"). La spec deja la CLI sin test de formato: lo que la cubre es T049.
- [ ] T053 [Paso 10] **Una** corrida real contra Overpass (Bogotá, 4711), **avisada antes**. Se anotan segundos, elementos, cuántos traen teléfono, el `name` real de la relación de Bogotá, si Croma trae geo y la forma de la respuesta, sin copiar ningún contacto. Si difiere de la fixture: se corrige la fixture y se vuelve a la Fase 8.

---

## Fase 12: Doc y cierre (Paso 11)

- [ ] T054 [P] [Paso 11] `docs/arquitectura-backend.md`: normalización, dedup (4 reglas, veto, geo, cola), cifrado (subclaves, AAD, catálogo), cómo mapear un CIIU nuevo y cómo agregar un host compartido. Primer corte si el tiempo aprieta (deuda en el PR).
- [ ] T055 Cierre: `uv run pytest -q`, `uv run lint-imports`, `scripts/migrar_local.sh` dos veces desde vacío. PR con las preguntas abiertas resueltas y los cortes aplicados, si los hubo.

---

## Dependencias

- T001 bloquea todo lo marcado con Pn. T002 bloquea T009 y T018.
- Fases 2, 3 y 4 en paralelo. La Fase 5 necesita T018 (cifrado) para T025–T026.
- Fase 6 necesita Fase 2 (normalización, geo). Fase 7 necesita Fases 5 y 6.
- Fase 8 necesita Fase 2 (mapeo) y T024 (para T042). T045–T046 en paralelo con T037–T044.
- Fase 9 necesita T044. Fase 10 necesita Fases 7, 8 y 9. Fase 11 necesita Fase 10.

## Cuándo cortar (de la spec, en este orden)

| Orden | Se corta | Tareas afectadas |
|---|---|---|
| 1 | Doc | T054 (deuda en el PR) |
| 2 | Desglose por regla en la CLI | T052 (fusionados en total) |
| 3 | Pares de plural en integración | `test_plural_largo_cae_en_fusion` y `test_plural_corto_cae_en_revision` de T035 |
| 4 | Limitador con reloj falso | `test_limitador_espera_un_segundo_entre_requests` de T041; `sleep(1)` fijo con `# ponytail:` en T044 |

No se cortan: regla 4 con geo (T029, T033), veto (T028, T033), cifrado (T017–T018, T025–T026), `wa.me` (T039–T040) y logs (T050).
