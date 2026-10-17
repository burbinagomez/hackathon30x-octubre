# Spec 008 — Dapta (dapta_csv) y CPQL

**Slice:** 008 · **Rama:** `feature/008-dapta-cpql` · **Tiempo:** domingo AM (≈ 3 h 30 si la 007 entregó completa; hasta ≈ 4 h 10 si le pasó su corte 3)
**Depende de:** 002 (`cumplimiento`, `RegistroCostos`, `costos` con `gratis`, unidad de trabajo con `SET LOCAL app.tenant_id`), 003 (`telefono_canal` y su cifrado, `whatsapp_osm`, `revision_dedup`), 004 (runner de evals), 005 (`v_costos`, `v_leads_icp`, `v_tablero_fuentes`, `lead_fuentes`, fixture A–J), 006 (`tipo_titular`, `encaje`), 007 (`contactos`, `respuestas` `interesado`, `v_leads_con_opt_out`, `DarDeBaja`). **Desbloquea:** 009 (`pide_no_contacto` por llamada bloquea WhatsApp), 012 (pantalla de cumplimiento: la transferencia a Dapta), 013 (el pitch muestra CPL y CPQL lado a lado).

> Cierra el embudo: los que respondieron `interesado` y tienen teléfono publicado salen a Dapta en un CSV, Dapta los llama, el resultado vuelve en otro CSV y cada minuto de llamada entra a `costos`. Con eso el tablero muestra el **CPQL** (PRD §4: costo total / demos agendadas) por fuente y por canal, al lado del CPL. Resuelve el pendiente de la 006: cómo se reparte el costo sin fuente de un lead que vino de dos fuentes.

## Para quién
- **Pyme usuaria:** ve cuánto le costó cada demo agendada según de dónde salió el lead, no solo cuánto le costó cada lead. Exporta e importa con dos botones.
- **Lead:** recibe una llamada solo si dijo que le interesa, es persona jurídica, publicó ese teléfono y no pidió la baja por ningún canal. Si en la llamada pide que no lo contacten, queda dado de baja en todos los canales.
- **Jurado:** CPQL calculado desde `costos`, con la cuenta hecha a mano en un test, y la cobertura de teléfono como métrica (sin teléfono = `no_calificable`).

## Qué hace
1. Lista los elegibles para llamada (`v_elegibles_dapta`) y los exporta a CSV para Dapta, con `fuentes` y `licencia` por lead y una línea de atribución al principio; cada exportado deja una fila en `calificaciones`.
2. Importa el CSV de resultados de Dapta: guarda el resultado, escribe `dapta_llamada` en `costos` y da de baja si el lead lo pide.
3. Atribuye a fuentes los costos con `lead_id` y sin `fuente` (enriquecimiento, contacto, LLM, Dapta), repartidos entre las fuentes del lead.
4. Suma al tablero `no_calificables`, `calificados`, `costo_embudo`, `cpql` y `tasa_calificacion`, y expone `v_cpql` por (fuente, canal).
5. Deja el dataset del eval `match_dapta` (encaje predicho vs. resultado de Dapta).

## Puertos y adaptadores que toca (`config/fuentes.yaml`)
- **`calificadores.dapta_csv`** (`habilitado: true`): adaptador nuevo detrás del puerto nuevo **`Calificador`**. `preparar(candidatos) -> bytes` arma el CSV; `leer_resultados(archivo: bytes) -> list[ResultadoLlamada | FilaRechazada]` lo parsea. El mapeo de columnas y de valores del CSV de Dapta vive en la config del adaptador (`columnas`, `valores`), `# [MENTORES]` hasta ver un export real.
- **`calificadores.dapta_api`** (`habilitado: false`, `# [MENTORES] hasta tener la doc`): no se implementa. Si llega la doc, entra por el mismo puerto y pasa la misma suite de contrato; el CPQL no cambia.
- **`RegistroCostos`**: tipo nuevo `dapta_llamada` (unidades = minutos, `dapta.usd_por_minuto`), `proveedor='dapta'`, `lead_id` set, `fuente=NULL`, `canal=NULL`. Lo escribe el caso de uso `ImportarResultados`, no el adaptador (ver Decisiones: desviación de VIII).
- **`RepositorioLeads`**: suma `elegibles_dapta()` (lee la vista) y nada más. El teléfono descifrado solo existe dentro de `ExportarElegibles`.
- **`DarDeBaja`** (007): `via` suma `llamada`.
- **Clasificación humana de respuestas** (007): `ClasificarRespuestaHumano` permite que un humano pase un `sin_clasificar` a `interesado` o `rechazo`, con `clasificador='humano'`. La 007 da un camino humano para la baja, pero no para marcar `interesado`. Sin este paso, si la 007 recortó su corte 2 (LLM), `v_elegibles_dapta` queda vacía para siempre.

## Skills que aplican
- `libro-costos`: `dapta_llamada` con `lead_id`; CPQL(fuente, canal) = Σ costos (descubrimiento + enriquecimiento + contacto + dapta) / demos agendadas; divisor 0 → "sin dato"; el test con el fixture de 10 leads, 2 fuentes y 2 canales, a mano.
- `cumplimiento-datos`: regla 2 (contactable por llamada = `juridica` y `telefono_canal` publicado), opt-out en todos los canales, la exportación como transferencia a un encargado (Dapta) con traza. Licencias: al compartir con un tercero datos derivados de OSM (ODbL) o de datos.gov.co (CC BY-SA 4.0), el archivo lleva atribución y licencia.
- `fuentes-publicas`: el teléfono `whatsapp_osm` cuenta como publicado (decisión del usuario) pero sale marcado con `origen_telefono` para que el operador lo vea.
- `slice-tdd`.

## Evals
| Eval | Componente bajo prueba | Forma | Significado | Ground truth | Umbral | k |
|---|---|---|---|---|---|---|
| `match_dapta` | `encaje` guardado por `ClasificarEncajeICP` (006), sin volver a correrlo | `resultado ∈ enum` | — (sin juez: precisión calculada en código) | el resultado de Dapta: `demo_agendada` = positivo, `no_califica` = negativo | 0.30 (provisional) | 1 |

Mide "¿los que marcamos `encaja` son los que Dapta califica?" (PRD §6b) como **precisión**, encajada en el contrato de la 004:
- **El dataset trae solo casos con `encaje='encaja'` y `resultado ∈ {demo_agendada, no_califica}`.** Un caso pasa si el resultado es `demo_agendada`. El `agregado` de la 004 (la fracción de todos los casos que pasan) es, por construcción, la precisión.
- Recall no se puede medir: un `no_encaja` nunca llega a Dapta.
- `no_contesta`, `numero_invalido` y `pide_no_contacto` no son etiqueta de calidad, así que quedan afuera.

**Juez y k.** La 004 no tiene "eval sin juez". Este slice suma `juez: ninguno`: sin juez, sin modelo, k=1 válido sin demostración. El fingerprint lleva `prompt` y `modelo` en null, y sigue incluyendo dataset, corte y umbral.

**Registro.** Solo entra a `evals.yaml` con **n ≥ 10 casos del dataset filtrado**. Con menos sale `DatasetInsuficiente` y el eval no se registra: registrado sin baseline, el runner sale 1 y deja la CI roja. Es lo más probable este fin de semana, y así se declara en el README: "match_dapta: n = X, sin medir" (principio IX).

**Dataset congelado por versión.** `app.cli evals match-dapta` no corre en la CI: escribe `casos/match_dapta.json`, que se commitea. Un import nuevo no cambia el dataset hasta que alguien lo regenera a propósito. Ese cambio vuelve obsoleto el fingerprint (`baseline_obsoleto`, 004), y quien lo regenera re-fija el baseline en el mismo PR con `--actualizar-baseline --motivo "dataset match_dapta vN, n = X"`.

El JSON pasa `test_jsons_de_evals_sin_datos_de_contacto`. El primer baseline se fija con `--motivo "primer baseline, slice 008"`.

## Flujo principal
0. **Antes de exportar, si hace falta:** un humano pasa los `sin_clasificar` a `interesado` o `rechazo`. Lo hace con `POST /respuestas/{id}/clasificar` (con sesión) o con `app.cli respuesta clasificar --id <id> --clase interesado`, que llaman a `ClasificarRespuestaHumano` (`clasificador='humano'`).
   - Solo se puede sobre un `sin_clasificar`. Un `pide_no_contacto` o un `rebote` no se re-clasifican nunca.
   - `rechazo` → `DarDeBaja(lead, via='humano')` en la misma transacción. Es el mismo criterio conservador de la 007: el "no" da de baja lo clasifique el LLM o un humano.
   - Para pedir la baja, sigue el camino de la 007: `POST /respuestas/{id}/baja`.
1. **Exportar** (`POST /calificaciones/exportar` con sesión, o `uv run python -m app.cli dapta exportar --salida dapta.csv`):
   1. Todo en **una** transacción:
      1. `pg_advisory_xact_lock` por tenant: dos exports en paralelo no sacan el mismo teléfono dos veces.
      2. `SELECT … FROM v_elegibles_dapta`, que ya deduplica por `telefono_hmac`.
      3. Descifra el teléfono y valida E.164 (`^\+\d{8,15}$`).
      4. `INSERT INTO calificaciones (estado='exportada', exportado_en=now(), canal_origen, origen_telefono)`, con `id` por `gen_random_uuid()`: no es secuencial.
      5. Arma el CSV con `Calificador.preparar`.

      Un teléfono inválido no sale ni crea fila: se cuenta como `telefono_invalido`. Un lead sin ninguna `licencia` en `lead_fuentes` tampoco sale: se cuenta como `sin_licencia`.
   2. Columnas: `ref` (el `calificacion_id`), `empresa`, `telefono`, `ciudad`, `sector` (descripción del CIIU), `origen_telefono`, `fuentes` y `licencia`. Sin `lead_id` ni email. Las dos salen de `lead_fuentes`, no de `cumplimiento`: `fuentes` lista las distintas del lead, en orden alfabético y unidas con `; `; `licencia` es una sola, la más restrictiva presente. Ver Decisiones: licencia en el export.
   2b. **Línea de atribución**, antes del encabezado: una fila de un solo campo, que va entre comillas porque lleva comas. Se arma con las fuentes presentes en los leads de **este** archivo, en este orden:
       - `datos_gov_co_rues` → "Datos: Confecámaras vía datos.gov.co, CC BY-SA 4.0";
       - `osm_overpass` → "© OpenStreetMap contributors, ODbL".

       Si están las dos, van unidas con `; `. Si ningún lead viene de esas fuentes (por ejemplo, solo Croma), la línea no va. Un export sin elegibles no la lleva.
   3. Contra CSV injection, todo campo de texto que empiece con `= + - @`, tab o CR se prefija con `'`. El teléfono no se toca: lo garantiza el regex.
   4. Respuesta en stream, con `Content-Disposition: attachment` y `Cache-Control: no-store`. No queda archivo en el server. El log dice cuántas filas y quién exportó, nada más.
2. **Dapta llama.** Fuera del sistema: el operador sube el CSV a la campaña de Dapta.
3. **Importar** (`POST /calificaciones/importar`, multipart con sesión, o `app.cli dapta importar --archivo resultados.csv`):
   1. Si `dapta.usd_por_minuto` es `null`: `TarifaPendiente` y no se escribe nada. Antes de tocar una fila.
   2. Límites de entrada:
      - ≤ 1 MB: se rechaza por `Content-Length` y se corta leyendo el stream (`read(1 MB + 1)`), no después de que FastAPI guardó el archivo entero;
      - ≤ 1000 filas;
      - UTF-8, con BOM aceptado.

      Si no cumple, `413` o `422`, sin eco del contenido.
   3. `Calificador.leer_resultados` mapea con la config:
      - `ref`;
      - `resultado ∈ {demo_agendada, no_califica, no_contesta, numero_invalido, pide_no_contacto}`;
      - `minutos`: 0–60, decimal;
      - `score`: 0–1, opcional;
      - `llamada_en`: opcional.

      Las columnas no mapeadas se ignoran y no se loguean: el CSV de Dapta puede traer el teléfono de vuelta. Un valor desconocido es `FilaRechazada(motivo)`, no una excepción. `FilaRechazada` lleva el motivo y el número de fila, **nunca el valor rechazado**: si el mapeo está mal y pone el teléfono en `resultado`, el teléfono no tiene que terminar en el resumen ni en el log.
   4. Por fila, en su transacción: `UPDATE calificaciones SET resultado, minutos, score, llamada_en, importado_en=now(), estado='importada' WHERE id=:ref AND resultado IS NULL`. Si afecta 1 fila, escribe `dapta_llamada` en la misma transacción:
      - `unidades = minutos`;
      - `ts = llamada_en` si cumple `exportado_en ≤ llamada_en ≤ now()`. Si no, `ts` es el momento del import: el CSV no es de confianza. Si afecta 0: mismo resultado ya guardado → `duplicada` (no-op); otro resultado → `conflicto` (no cambia nada; lo resuelve un humano); ref inexistente o de otro tenant (RLS) → `ref_desconocida`.
   5. `pide_no_contacto` → `DarDeBaja(lead, via='llamada')` en la misma transacción.
   6. Un lead que se dio de baja **después** del export igual guarda su resultado y su costo (la llamada ocurrió) y se cuenta como `baja_posterior`.
   7. Devuelve el resumen: `importadas`, `duplicadas`, `rechazadas` por motivo, `baja_posterior`. Sin empresa ni teléfono.
4. **Pendientes** (`app.cli dapta pendientes`): lista los `ref` exportados sin resultado y marca los que tienen baja posterior, para sacarlos a mano de la campaña de Dapta. Con CSV no hay forma de avisarle a Dapta. `# ponytail: con dapta_api la baja se propaga sola`.
5. **Tablero.** `GET /tablero/fuentes` suma las columnas nuevas y, con `dapta.provisional: true`, `avisos: ["tarifa_dapta_provisional"]`.
6. **Dataset del eval** (`app.cli evals match-dapta`): escribe `backend/evals/casos/match_dapta.json` con `{caso: sha256(lead_id)[:12], fuente, encaje_predicho, resultado}`. Trae solo los casos con `encaje='encaja'` y resultado `demo_agendada` o `no_califica`.
## Terminado cuando (tests que hoy fallan)
**Dominio** (`backend/tests/unit/calificacion/`)
- `test_resultado.py::test_mapea_valores_de_dapta_desde_config`, `::test_valor_desconocido_es_fila_rechazada`, `::test_minutos_fuera_de_0_60_se_rechaza`, `::test_score_fuera_de_0_1_se_rechaza`, `::test_ref_que_no_es_uuid_se_rechaza`.
- `test_csv_seguro.py::test_prefija_formulas_en_texto_libre` (`=HYPERLINK(…)` → `'=HYPERLINK(…)`, también `+`, `-`, `@`, tab, CR), `::test_telefono_e164_no_se_escapa`.
- `backend/tests/unit/contacto/test_dar_de_baja.py::test_acepta_via_llamada` (se suma a la 007).

**Clasificación humana** (`backend/tests/integration/test_respuestas.py`, se suma a la 007)
- `::test_humano_clasifica_sin_clasificar_como_interesado`: queda `clasificacion='interesado'` y `clasificador='humano'`, y el lead aparece en `v_elegibles_dapta`. Sin sesión, `401`. Lo mismo vale para `app.cli respuesta clasificar`.
- `::test_humano_no_reclasifica_pide_no_contacto_ni_rebote`: sale `409` y nada cambia.
- `::test_humano_clasifica_rechazo_da_de_baja`: el lead entra a `v_leads_con_opt_out` y `solicitudes` tiene `{tipo:'baja', via:'humano'}`.

**Elegibles** (`backend/tests/integration/test_elegibles_dapta.py`, sobre `fixture_interesados`: ver Tablero)
- `::test_interesado_juridica_con_telefono_es_elegible`: A y E.
- `::test_interesado_sin_telefono_no_es_elegible`: H.
- `::test_sin_respuesta_interesado_no_es_elegible`: C (rebote), B (pendiente), D.
- `::test_no_juridica_nunca_es_elegible[natural|desconocido]`: G (`desconocido`), y G pasado a `natural`, aunque se le sume un `interesado`.
- `::test_mismo_telefono_hmac_que_uno_exportado_no_sale`: un lead con NIT distinto comparte `telefono_hmac` con A, que ya está exportado → no sale. Lo mismo para un lead en el que se fusionó A después del export.
- `::test_dos_elegibles_con_mismo_telefono_salen_una_vez`: sale uno solo, el de la primera respuesta `interesado`.
- `::test_opt_out_por_cualquier_via_excluye`: baja por email, por enlace y un lead que comparte `telefono_hmac` con uno dado de baja (la `v_leads_con_opt_out` de la 007).
- `::test_excluye_fusionados_revision_pendiente_y_sin_cumplimiento`.
- `::test_ya_exportado_no_vuelve_a_salir`.
- `::test_whatsapp_osm_sale_con_origen_telefono`: un lead `juridica` con `telefono_canal='whatsapp_osm'` e `interesado` sale con `origen_telefono='whatsapp_osm'`.

**Exportar** (`backend/tests/integration/test_exportar_dapta.py`, sobre `fixture_interesados`)
- `::test_exporta_y_crea_calificacion_en_la_misma_transaccion`: si `preparar` falla, no queda ninguna fila en `calificaciones`.
- `::test_csv_tiene_columnas_ref_y_telefono_e164`: 2 filas (A, E), `ref` = `calificacion_id`, sin `lead_id` ni email.
- `::test_telefono_invalido_no_sale_y_se_cuenta`.
- `::test_export_sin_elegibles_devuelve_solo_encabezado`.
- `::test_export_csv_lleva_atribucion_y_licencia[caso]`: falla si falta la línea de atribución que corresponde o si alguna fila tiene `licencia` vacía. Compara la primera línea exacta y `fuentes` y `licencia` por `ref`:
  - `cs_y_osm` (A y E del fixture, sin fusionar) → la línea dice solo "© OpenStreetMap contributors, ODbL". A sale con `fuentes='croma_supersociedades_co'` y la licencia de Croma de `fuentes.yaml`; E con `fuentes='osm_overpass'` y `licencia='ODbL'`;
  - `fusionado_croma_y_osm`: se fusiona E en A (`E.fusionado_en = A`, sus `lead_fuentes` se mueven, como en 003). E deja de ser elegible (filtro `fusionado_en IS NULL`) y solo sale A, con `fuentes='croma_supersociedades_co; osm_overpass'` y `licencia='ODbL'` — gana sobre la de Croma, por la regla de Decisiones. La fila de `cumplimiento` de A sigue diciendo solo Croma: este caso falla si `fuentes`/`licencia` se leen de ahí. La línea de atribución lleva solo "© OpenStreetMap contributors, ODbL": no hay datos.gov.co en este caso;
  - `fusionado_datosgov_y_osm`: se siembra en E una `lead_fuentes` de `datos_gov_co_rues` con `CC-BY-SA-4.0`, como la que deja una fusión (003). Es el caso más probable en producción, porque un lead de datos.gov.co solo es llamable cuando se fusiona con OSM (011). E sale con `fuentes='datos_gov_co_rues; osm_overpass'` y `licencia='CC-BY-SA-4.0'`, que gana sobre ODbL. La línea lleva las dos atribuciones, en orden: "Datos: Confecámaras vía datos.gov.co, CC BY-SA 4.0; © OpenStreetMap contributors, ODbL";
  - `solo_croma` (E fuera) → sin línea de atribución, y la primera línea es el encabezado;
  - `sin_licencia`: la `lead_fuentes` de E queda con `licencia` NULL. E no sale, se cuenta como `sin_licencia` y no crea fila en `calificaciones`.

**Importar** (`backend/tests/integration/test_importar_dapta.py`, tarifa de prueba `dapta.usd_por_minuto = 0.10`)
- `::test_demo_agendada_guarda_y_registra_dapta_llamada`: A con 3 min → 1 fila `tipo='dapta_llamada'`, `unidades=3`, `costo_unitario=0.10`, `proveedor='dapta'`, `lead_id=A`, `fuente=NULL`, `canal=NULL`, `ts = llamada_en`.
- `::test_sin_llamada_en_usa_el_momento_del_import` y `::test_llamada_en_fuera_de_rango_usa_el_momento_del_import`: un `llamada_en` anterior a `exportado_en` o en el futuro.
- `::test_numero_invalido_con_cero_minutos_escribe_fila_en_cero`.
- `::test_reimportar_el_mismo_archivo_es_idempotente`: dos veces → 1 fila de costo por llamada; el segundo resumen dice `duplicadas=2`.
- `::test_resultado_distinto_para_ref_ya_importada_es_conflicto`: no cambia el resultado ni escribe costo.
- `::test_ref_desconocida_o_de_otro_tenant_se_rechaza`.
- `::test_valor_desconocido_se_rechaza_sin_costo_y_el_resto_entra`: una de las filas trae `+573001112233` en la columna mapeada a `resultado`, y ese valor no aparece ni en el resumen ni en `caplog`.
- `::test_pide_no_contacto_da_de_baja_via_llamada`: el lead entra a `v_leads_con_opt_out` y `solicitudes` tiene `{tipo:'baja', via:'llamada'}`.
- `::test_baja_posterior_al_export_guarda_y_se_cuenta`.
- `::test_tarifa_null_falla_sin_escribir_nada`.
- `::test_columna_telefono_del_csv_no_se_persiste`: el CSV trae `telefono`; no aparece en ninguna columna de la base.
- `::test_pendientes_lista_bajas_posteriores`.

**API** (`backend/tests/integration/test_api_calificaciones.py`)
- `::test_exportar_headers_attachment_y_no_store`. Las dos rutas entran solas a `test_sin_token_da_401[ruta]` (005): no están en `RUTAS_PUBLICAS`.
- `::test_importar_rechaza_mas_de_1mb_y_no_utf8`: `413` y `422`, sin eco del contenido. El `413` sale sin leer más de 1 MB + 1 del stream.
- `::test_importar_devuelve_resumen_sin_contacto`.
- `test_api_busquedas.py::test_tablero_incluye_columnas_de_calificacion` (se suma a la 005): las columnas nuevas serializadas con los números de abajo.
- `::test_tablero_avisa_tarifa_dapta_provisional`.

**Tablero** (`backend/tests/integration/test_vistas_tablero.py`)
Son dos fixtures de pytest compuestos sobre el A–J de la 005/006/007. Los asserts de la 005–007 siguen corriendo sobre el fixture base y no cambian. Estos dos los leen solo los tests de la 008:
- **`fixture_interesados`**: base + E y H. Lo usan Elegibles y Exportar, porque todavía no tiene calificaciones.
  - E: `juridica`, `telefono_canal='sitio_web'`, `email_canal='sitio_web'`, contacto email `enviado` + respuesta `interesado`, `email_envio` en 0 con `gratis`.
  - H: `juridica`, `email_canal='sitio_web'`, **sin teléfono**, contacto email `enviado` + `interesado`, `email_envio` en 0 con `gratis`.
- **`fixture_calificaciones`**: `fixture_interesados` + las calificaciones + las filas 10–13. Lo usan Tablero y API.
  - Calificaciones: A `demo_agendada` 3 min y E `demo_agendada` 2 min, las dos con `canal_origen='email'`.
- Filas de costos (las `email_envio` en 0 no mueven ningún número):

| fila | tipo | lead | fuente | canal | unidades × costo |
|---|---|---|---|---|---|
| 10 | `croma_consulta` | A | NULL | NULL | 1 × 0.04 |
| 11 | `web_fetch` | C | NULL | NULL | 1 × 0.10 |
| 12 | `dapta_llamada` | A | NULL | NULL | 3 × 0.10 |
| 13 | `dapta_llamada` | E | NULL | NULL | 2 × 0.10 |

Cuenta a mano (lista / real; las filas nuevas no son gratis):
- Reparto de las filas sin fuente entre las fuentes de `lead_fuentes`: A → cs (0.04 + 0.30); C → 0.05 cs + 0.05 osm; E → osm (0.20). cs suma 0.39, osm 0.25.
- `costo_embudo`: cs = 1.35 + 0.39 = **1.74** / 0.95 + 0.39 = **1.34**; osm = 1.40 + 0.25 = **1.65** / **1.65**; TOTAL = 2.82 + 0.64 = **3.46** / 2.42 + 0.64 = **3.06** (la fila 4, sin lead, queda en `sin_atribuir`: 1.74 + 1.65 + 0.07 = 3.46).
- `calificados`: cs 1 (A), osm 1 (E), TOTAL 2.
- `cpql`: cs **1.74** / **1.34**; osm **1.65** / **1.65**; TOTAL **1.73** / **1.53**. Contra el CPL de la 005: cs ≈ 5.2×, osm 8.25× (PRD §4: 4–10×).
- `no_calificables`: cs 0, osm 1 (H), TOTAL 1. `tasa_calificacion` = calificados / interesados: cs 1/1 = 1.0, osm 1/2 = 0.5, TOTAL 2/3.
- `v_cpql`: (cs, email) 1.74 / 1.34 → **1.74 / 1.34**; (cs, whatsapp) costo 1.39 / 0.99 (sin la fila 7 ni la llamada de A), 0 calificados → **NULL**; (osm, email) 1.65 − 0.30 de la fila 8 = **1.35 / 1.35**; (osm, whatsapp) 0 calificados → **NULL**; (TOTAL, email) 3.16 / 2.76 → **1.58 / 1.38**.

Tests:
- `::test_costo_embudo_reparte_lo_sin_fuente_entre_las_fuentes_del_lead`: cs 1.74/1.34, osm 1.65/1.65 (C: 0.05 a cada una).
- `::test_costo_embudo_conserva_el_total`: Σ fuentes + `sin_atribuir` = TOTAL = Σ `v_costos`, tolerancia 1e-9.
- `::test_lead_sin_lead_fuentes_queda_sin_atribuir`: una fila con `lead_id` de un lead sin `lead_fuentes` no se pierde: va a `sin_atribuir` y el total se conserva.
- `::test_cpql_por_fuente` y `::test_cpql_sin_calificados_es_null`.
- `::test_cpql_por_canal_excluye_costos_de_otro_canal`: la fila 8 no entra a (osm, email); la llamada de A (canal de origen email) no entra a (cs, whatsapp).
- `::test_no_calificables_y_tasa_calificacion`: tolerancia 1e-9, porque 2/3 es periódico.
- `::test_dapta_no_cambia_costo_por_respuesta`: `v_costo_por_respuesta` da lo mismo con y sin las filas 12–13 (van con `canal=NULL`).

**Front**
- `frontend/src/tablero/Tablero.test.tsx::muestra_calificados_cpql_y_tasa`: CPQL y CPL lado a lado, NULL como "sin dato", tasa como "67 %"; `::avisa_tarifa_dapta_provisional`.
- `frontend/src/calificacion/Calificacion.test.tsx::exportar_descarga_csv_y_muestra_cuantos` y `::importar_muestra_resumen_por_motivo`.

**Cifrado y logs**
- `backend/tests/arquitectura/test_contacto_no_aparece_en_logs.py::test_export_e_import_dapta_no_loguean_contacto`: exportar + importar (con un CSV que trae `telefono`) con `caplog` en `DEBUG` sobre todos los loggers: ni `+573001112233` ni la empresa aparecen.
- La guarda de catálogo de la 003 sigue verde sin excepciones: `calificaciones` no guarda ningún dato de contacto.

**Migración** (`backend/tests/integration/test_migraciones.py`)
- `::test_migracion_0008_sobre_0007_con_datos`: base en `0007` con contactos y respuestas → `upgrade 0008` no falla.
- `::test_v_tablero_fuentes_conserva_columnas_previas_en_orden`: las columnas de la 005–007 siguen en el mismo orden; las nuevas, al final.

**RLS**
- `test_rls.py::test_tenant_b_no_accede_a_datos_de_a[calificaciones]`. `test_privilegios_supabase.py` la toma sola de `pg_tables`.

**Contratos** (`backend/tests/contratos/test_calificador.py`, parametrizado sobre `dapta_csv` y `CalificadorFalso`)
- `::test_preparar_devuelve_una_fila_por_candidato_con_su_ref`, `::test_leer_resultados_ida_y_vuelta` (lo que sale de `preparar` + un resultado por ref vuelve mapeado), `::test_valor_desconocido_es_fila_rechazada_no_excepcion`, `::test_columnas_no_mapeadas_se_ignoran`, `::test_archivo_sobre_limite_es_entrada_invalida`.
- `::test_preparar_lleva_fuentes_y_licencia_por_fila`: un candidato sin licencia es error de contrato. Así `dapta_api`, cuando exista, también las manda.
- `::test_leer_resultados_ignora_lineas_antes_del_encabezado`: lo que esté antes de la fila con la columna mapeada a `ref` se ignora. Así la ida y vuelta pasa con la línea de atribución, y también si Dapta la devuelve o la saca.

**Arquitectura**
- `test_import_linter.py`: el módulo `calificacion` respeta las capas; el dominio no importa `csv` ni `fastapi`.
- `test_costos_por_adaptador.py`: `DaptaCSV` queda afuera **a propósito**, igual que `SinClasificar` en la 007: no hace operación de salida (la llamada la hace Dapta). `dapta_api`, cuando exista, entra a la lista.

**Evals**
- `backend/tests/unit/evals/test_match_dapta.py`:
  - `::test_dataset_solo_trae_encaja_con_demo_o_no_califica`;
  - `::test_agregado_es_la_precision_de_encaja`: 3 demos y 1 no_califica dan 0.75;
  - `::test_menos_de_10_casos_es_dataset_insuficiente`, contando sobre el dataset filtrado;
  - `::test_json_sin_datos_de_contacto`.
- `backend/tests/unit/evals/test_runner.py`:
  - `::test_eval_sin_juez_admite_k1`;
  - `::test_fingerprint_sin_juez_cambia_con_el_dataset`: regenerar el JSON da `baseline_obsoleto`.

  Hoy los dos fallan: la 004 no tiene `juez: ninguno`.

## Fuera del alcance
- **`dapta_api`**: sigue OFF hasta tener la doc `# [MENTORES]`. Cuando llegue, implementa `Calificador` y pasa la suite de contrato.
- **Volver a llamar a un `no_contesta`**: un lead se llama una vez (`UNIQUE (tenant_id, lead_id)`). `# ponytail: un intento por lead; una tabla de intentos si el no_contesta resulta alto`.
- **`minutos_humanos` en el CPQL**: la tarifa existe (`humano.usd_por_minuto = 0.25`) pero no se mide el tiempo del operador este fin de semana. `# ponytail: entra como fila con lead_id cuando se mida`.
- **Re-tarifar** las filas `dapta_llamada` si la tarifa provisional cambia. El aviso queda visible en el tablero.
- **Re-exportar** un CSV perdido: los exportados sin resultado se ven con `dapta pendientes`.
- **Llamadas propias**: las hace Dapta (PRD).
- **Recall de `match_dapta`**: un `no_encaja` nunca se llama.
- **Contactos por WhatsApp**: 009. `canal_origen` ya admite `whatsapp`.

## Decisiones técnicas
**Módulo** `backend/app/modulos/calificacion/{dominio,aplicacion,infraestructura/adaptadores}`. Dominio: `ResultadoLlamada`, `FilaRechazada`, `CandidatoLlamada`, `csv_seguro`. Aplicación: `ExportarElegibles`, `ImportarResultados`, `ListarPendientes`. Adaptadores: `dapta_csv` (con `csv` de la stdlib).

**Calificado** = `demo_agendada` de un lead que está en `v_leads_icp` (PRD l.53). `no_calificable` es una columna derivada (interesado de `v_leads_icp` sin `telefono_canal`), no una fila: no hay nada que guardar.

**Reparto de lo sin fuente (pendiente de la 006).** Toda fila de `v_costos` con `fuente IS NULL` y `lead_id` set se reparte **en partes iguales** entre las fuentes distintas de ese lead en `lead_fuentes`. Se usa `lead_fuentes` y no `v_leads_icp`: el costo existe aunque el lead no encaje, y el CPQL incluye el desperdicio igual que el CPL. Sin fuentes, o sin `lead_id` (fila 4), queda en `sin_atribuir`. La conservación del total es un test. Partes iguales porque no hay criterio mejor: cualquier peso inventaría una causalidad que no medimos.

**CPQL(fuente, canal).** Para `dapta_llamada`, el canal efectivo es el `canal_origen` de su calificación. Los costos con canal se cuentan solo en su canal; los que no tienen canal (lotes, enriquecimiento) se cuentan en todos, porque el descubrimiento no depende del canal. Por eso Σ por canal ≠ total, y está bien: CPQL(f, c) responde "cuánto cuesta una demo si salgo por este canal". Con un solo canal activo, CPQL(f, email) = CPQL(f) salvo el contacto por otro canal (fila 8).

**`dapta_llamada` con `canal=NULL`** en `costos`, para que no infle `v_costo_por_respuesta` (la llamada es posterior a la respuesta). El canal para el CPQL sale de `calificaciones.canal_origen`.

**Desviación de VIII (documentada).** VIII pide la fila "en el momento en que ocurre". Con CSV nos enteramos de la llamada al importar: la fila se escribe en el import con `ts = llamada_en` (el momento real) si Dapta lo trae. Con `dapta_api` sería en tiempo real. La alternativa, una fila estimada al exportar, registraría llamadas que quizás no ocurren.

**Tarifa.** `config/tarifas.yaml`: `dapta.usd_por_minuto: null  # [MENTORES]` y `dapta.provisional: false`. Con `null`, el import falla con `TarifaPendiente`. El equipo puede poner un valor provisional con `provisional: true`, y el tablero lo avisa.

**Sin token HMAC en `ref`.** El `calificacion_id` crudo alcanza: la ruta exige sesión y RLS filtra por tenant. Un `ref` de otro tenant es `ref_desconocida`. No se expone el `lead_id`.

**La transferencia a Dapta** queda trazada en `calificaciones.exportado_en`, por lead. La pantalla de cumplimiento de la 012 la lee.

**Licencia en el export.** Compartir con Dapta datos derivados de OSM o de datos.gov.co es compartirlos con un tercero, así que ODbL y CC BY-SA piden atribución y licencia. `fuentes` y `licencia` salen de `lead_fuentes` y no de `cumplimiento`. Un lead fusionado (003, 005) conserva una sola fila de `cumplimiento`, la del primero, pero suma las `lead_fuentes` del absorbido: si se leyera solo `cumplimiento`, un lead con una licencia abierta podría salir con la de Croma. Por eso existe el caso `fusionado_croma_y_osm`.
- `fuentes` lista todas las distintas del lead en `lead_fuentes`, unidas con `; ` y en orden alfabético (`string_agg(DISTINCT fuente, '; ' ORDER BY fuente)`). Sin `ORDER BY`, Postgres no garantiza el orden y el test sería inestable.
- `licencia` es una sola, la más restrictiva presente, en este orden: `CC-BY-SA-4.0` > `ODbL` > la de Croma ("datos públicos vía Croma; no redistribuir"). Las abiertas ganan porque imponen una obligación activa (atribuir, compartir bajo la misma licencia) que la de Croma no tiene: esa solo pide no redistribuir, y Dapta recibe los datos como encargado para llamar en nombre de la pyme, no para redistribuirlos.
- La línea de atribución del archivo se arma con las fuentes abiertas presentes en los leads exportados (no con `licencia` por fila), con el mismo mapa y orden de `v_atribuciones` (005).
- `# ponytail:` los dos textos de la línea viven en el dominio de `calificacion`. Son una segunda copia del mapa de `v_atribuciones` (005), con el nombre de la licencia agregado. Si se suma una tercera fuente con atribución, los dos mapas pasan a una columna `atribucion` en `config/fuentes.yaml`, como dice la 005.

**Migración `0008_calificaciones.py`** (a mano, con `GRANT` a `app_rt`):

| Tabla / vista | Definición |
|---|---|
| `calificaciones` | `id uuid PK`, `tenant_id`, `lead_id FK`, `canal_origen text NOT NULL CHECK (email, whatsapp)`, `origen_telefono text NOT NULL CHECK (whatsapp_comercial, sitio_web, osm_contacto, whatsapp_osm)`, `estado text NOT NULL CHECK (exportada, importada)`, `exportado_en timestamptz NOT NULL`, `resultado text NULL CHECK (demo_agendada, no_califica, no_contesta, numero_invalido, pide_no_contacto)`, `minutos numeric NULL CHECK (minutos BETWEEN 0 AND 60)`, `score numeric NULL CHECK (score BETWEEN 0 AND 1)`, `llamada_en`, `importado_en`, `CHECK ((estado = 'importada') = (resultado IS NOT NULL))`, `UNIQUE (tenant_id, lead_id)`. RLS por `tenant_id`; `GRANT SELECT, INSERT, UPDATE`. |
| `respuestas` | El CHECK de `clasificador` suma `humano`. |
| `v_elegibles_dapta` | Columnas: `lead_id`, `canal_origen` (el del primer contacto con respuesta `interesado`), `origen_telefono`. Condiciones: `tipo_titular='juridica'`; `telefono_canal IS NOT NULL`; está en `v_leads_icp`; está fuera de `v_leads_con_opt_out`; `fusionado_en IS NULL`; no tiene `revision_dedup` pendiente; tiene fila en `cumplimiento`; no tiene fila en `calificaciones`; su `telefono_hmac` no es el de ningún lead con calificación. Al final, `DISTINCT ON (telefono_hmac)`, ordenado por la primera respuesta `interesado`. |
| `v_costo_atribuido` | Por fila de `v_costos`: `fuente_atrib`, `canal_ef` (`canal_origen` para `dapta_llamada`, `canal` para el resto), `monto_lista`, `monto_real`. Con `fuente`, tal cual; sin `fuente` y con `lead_id` con fuentes, una fila por fuente distinta con monto / n; si no, `sin_atribuir`. |
| `v_cpql` | Por (`fuente_atrib`, canal ∈ {email, whatsapp}) + `TOTAL`: `costo_lista`, `costo_real` (Σ `v_costo_atribuido` con `canal_ef IS NULL OR canal_ef = canal`), `calificados` (demos de leads de `v_leads_icp` de esa fuente con `canal_origen = canal`), `cpql_lista`, `cpql_real`. Divisor 0 → NULL. |
| `v_tablero_fuentes` | `CREATE OR REPLACE`, columnas nuevas al final: `no_calificables`, `calificados`, `costo_embudo_lista`, `costo_embudo_real`, `cpql_lista`, `cpql_real`, `tasa_calificacion`. Si la 007 cortó su corte 3, sus columnas y `v_costo_por_respuesta` entran acá antes que estas. |

Todas las vistas con `security_invoker = true`. No redondean.

## Plan de tareas (TDD, en orden)
**Corte 1: exportar, importar, costos y CPQL** (≈ 2 h 15; + 40 min si la 007 cortó su corte 3)
0. **Solo si la 007 cortó su corte 3:** sus columnas del tablero y `v_costo_por_respuesta`, con sus tests de la 007 en rojo → verde (≈ 40 min). Va primero, porque la tarea 2 (`test_v_tablero_fuentes_conserva_columnas_previas_en_orden`) y la tarea 7 (`test_dapta_no_cambia_costo_por_respuesta`) las necesitan.
1. Rojo: dominio (`test_resultado.py`, `test_csv_seguro.py`, `test_acepta_via_llamada`) → verde.
1b. Rojo: clasificación humana (`test_humano_clasifica_sin_clasificar_como_interesado`, `test_humano_no_reclasifica_pide_no_contacto_ni_rebote`) → verde con `ClasificarRespuestaHumano` y la CLI (≈ 15 min).
2. Migración `0008` + `test_migracion_0008_sobre_0007_con_datos` + `test_rls[calificaciones]` + `test_v_tablero_fuentes_conserva_columnas_previas_en_orden`.
3. Rojo: `test_elegibles_dapta.py` → verde con `v_elegibles_dapta`.
4. Rojo: `test_calificador.py` (contrato) → verde con `DaptaCSV` y `CalificadorFalso`.
5. Rojo: `test_exportar_dapta.py` → verde con `ExportarElegibles` (CLI).
6. Rojo: `test_importar_dapta.py` → verde con `ImportarResultados` y `ListarPendientes` (CLI).
7. Rojo: los tests de vistas de `test_vistas_tablero.py` → verde con `v_costo_atribuido`, `v_cpql` y el replace de `v_tablero_fuentes`. **El advisor revisa la cuenta a mano antes del verde** (`slice-tdd`: fórmula de costos).
   Cierre del corte 1: `test_contacto_no_aparece_en_logs`, import-linter, `test_costos_por_adaptador` y la prueba manual con Dapta: subir el CSV a una campaña de prueba con un teléfono propio del equipo, bajar el export de resultados y mapear sus columnas en la config. Los nombres reales de columnas y valores se documentan en el PR.

**Corte 2: API, tablero y front** (≈ 45 min)
8. Rojo: `test_api_calificaciones.py` + los dos asserts que se suman a `test_api_busquedas.py` → verde.
9. Rojo: `Tablero.test.tsx` y `Calificacion.test.tsx` → verde.
10. (La parte de back que la 007 haya cortado va en la tarea 0. El front de Mensajes y Respuestas va a la 010, como dice la 007.)

**Corte 3: eval `match_dapta`** (≈ 30 min)
11. Rojo: `test_match_dapta.py` + `test_eval_sin_juez_admite_k1` → verde con `app.cli evals match-dapta`.
12. Con n ≥ 10, registrar en `evals.yaml` y fijar el primer baseline; si no, anotarlo en el README.

13. Doc, en el mismo cambio que cada bloque: `docs/arquitectura-backend.md`, módulo `calificacion` y la fórmula del CPQL; `docs/arquitectura-frontend.md`, página Calificación. En `docs/prd.md` l.149, la fórmula del CPQL suma "enriquecimiento", como ya dicen la skill `libro-costos` y esta spec.

**Orden de corte**, si no alcanza el tiempo (lo que se corta, a dónde va):
1. **Corte 3, eval:** queda pendiente y la 013 lo lista. El README dice "match_dapta: sin medir".
2. **Corte 2:** la exportación y la importación siguen por CLI, y el CPQL se lee de `v_cpql` con `psql` o con `GET /tablero/fuentes` sin front. El front pasa a la 010.
3. **El corte 1 no se corta.** Sin CPQL calculado desde `costos` no hay respuesta a la pregunta del reto.

## Riesgos
- **El formato del CSV de Dapta es desconocido** `# [MENTORES]`. Mitigación: mapeo por config y la prueba manual del cierre del corte 1. Si Dapta no exporta resultados, el operador los carga a mano en una plantilla con las mismas columnas, y el flujo no cambia.
- **Dapta podría exigir el encabezado en la primera línea** `# [MENTORES]`. Se ve en la prueba manual del cierre del corte 1. Si la rechaza, la línea de atribución pasa a un `atribucion.txt` que se baja junto al CSV, y `fuentes` y `licencia` siguen por fila. El test cambia en el mismo PR.
- **Tarifa de Dapta desconocida:** sin ella no se importa. Con la provisional, las filas quedan con ese valor y el tablero lo avisa. Re-tarifar queda fuera.
- **Pocas demos este fin de semana:** el CPQL va a salir con n = 1 o 2, o "sin dato". Se muestra `calificados` al lado y no se esconde.
- **Teléfonos `whatsapp_osm`** (confianza baja): pueden ser celulares personales del dueño. Solo salen de un lead `juridica` que respondió `interesado`, y van marcados con `origen_telefono` para que el operador decida.
- **El CSV exportado vive en la máquina del operador** con teléfonos en claro. Fuera de nuestro control: la página de Calificación dice "borralo después de subirlo a Dapta".
- **Baja posterior al export:** Dapta ya tiene el número. Mitigación: `dapta pendientes` y sacarlo a mano de la campaña.
- **Cuándo cortar:** ver el orden de corte. Lo que nunca se corta es el corte 1.
