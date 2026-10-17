# Spec 009 — WhatsApp acotado (whatsapp_meta)

**Slice:** 009 · **Rama:** `feature/009-whatsapp-acotado` · **Tiempo:** domingo, si hay tiempo (≈ 3 h 30) · **Carril:** @burbinagomez
**Depende de:** 002 (`cumplimiento`, `RegistroCostos`, unidad de trabajo con `SET LOCAL app.tenant_id`, `ConfigInvalida`), 003 (`leads.telefono_cifrado`/`telefono_hmac`/`telefono_canal`, cifrado con AAD), 005 (auth, `v_costos`, fixture A–J con la fila 8 `whatsapp`), 006 (`tipo_titular`, `telefono_canal='sitio_web'` de A y C), 007 (`contactos`, `respuestas`, `plantilla.validar`, `AprobarMensaje`, `DarDeBaja`, `v_leads_con_opt_out`, `v_tablero_fuentes`, `v_costo_por_respuesta`, `clasificadores.sin_clasificar`, `RUTAS_PUBLICAS`, fixture extendido de Tablero). La 008 no es requisito. **Desbloquea:** 012 (pantalla de cumplimiento: opt-in y tasa de bloqueo), 013 (el pitch compara WhatsApp con email).

> WhatsApp **no** es primer toque frío: Meta exige opt-in y el contacto en frío "no está oficialmente permitido" (PRD §2b). Este slice abre WhatsApp con tres condiciones:
> - el lead **pidió** que le escriban por ahí en una respuesta;
> - el número es el **comercial que la empresa publicó** (PRD l.18, l.62, l.158);
> - un humano registra el opt-in.
>
> Además: plantilla aprobada por Meta que cumple la regla 7, aprobación humana por mensaje, tope diario y freno automático si la tasa de bloqueo llega al 1 %. El canal nace apagado (`whatsapp_meta.habilitado: false`). Se prende solo con la validación escrita del dueño, la tarifa cargada y las variables de entorno. Si el domingo 3pm no está, se corta entero y el MVP es solo email (constitución, reglas del proyecto).

## Para quién
- **Pyme usuaria:** cuando un lead le contesta el email con "escríbanme por WhatsApp", lo registra con un clic y le llega una plantilla al WhatsApp comercial de esa empresa, sin salirse de las reglas de Meta.
- **Lead:** recibe WhatsApp solo si lo pidió y solo en el número que su empresa publicó. El mensaje viene identificado, con el porqué, de dónde salió el contacto y cómo salir ("responda BAJA"). Un BAJA por WhatsApp lo da de baja en todos los canales.
- **Jurado:** ve en el tablero WhatsApp al lado de email: contactados, entregados, bloqueos, tasa de bloqueo y `costo_por_respuesta('whatsapp')`, calculados desde `costos`.

## Qué hace
1. Registra un opt-in de WhatsApp ligado a una respuesta `interesado` del lead, sobre el teléfono comercial publicado del lead. El humano no tipea ningún número.
2. Arma el mensaje desde una plantilla fija aprobada por Meta, lo valida con la regla 7 (versión WhatsApp) y lo deja en `pendiente_aprobacion` para un humano, como en la 007.
3. Envía los aprobados por la Cloud API de Meta, con tope diario de intentos y freno por tasa de bloqueo. Escribe `whatsapp_plantilla` en `costos` por cada intento. Nunca reenvía solo.
4. Recibe el webhook de Meta firmado, con estados de entrega y mensajes entrantes:
   - un BAJA da de baja sin LLM;
   - un bloqueo de Meta da de baja y cuenta para el freno;
   - el resto se guarda `sin_clasificar` y se clasifica fuera del webhook;
   - nunca responde solo.
5. Suma WhatsApp al tablero: tasa de bloqueo por canal y `costo_por_respuesta('whatsapp')`, que deja de ser NULL.

## Puertos y adaptadores que toca (`config/fuentes.yaml`)
- **`canales_contacto.whatsapp_meta`** (`habilitado: false` hasta la validación escrita del dueño): adaptador nuevo detrás del puerto **`CanalContacto`** de la 007.
  - **Métodos:**
    - `enviar(mensaje) -> message_id`: manda la plantilla por `httpx` a la Graph API (`# [VALIDAR]` versión y forma del payload);
    - `verificar(cuerpo: bytes, headers) -> bool`: firma de Meta;
    - `parsear(cuerpo: bytes) -> list[MensajeEntrante | EstadoEntrega]`.

    La API no conoce a Meta: llama a `verificar` y a `parsear` del adaptador.
  - **Config que ya existe y este slice hace cumplir:**
    - `solo_numeros_comerciales_publicados: true`: el número es `leads.telefono_cifrado` con `telefono_canal ∈ {sitio_web, osm_contacto}`. `whatsapp_osm` queda fuera porque puede ser el celular personal del tendero (003).
    - `tasa_bloqueo_max: 0.01`.
  - **Config nueva:**
    - `validacion_dueno: null`: fecha y referencia de la validación escrita en `docs/decisiones.md`. Con `habilitado: true` y `null`, la app no arranca.
    - `max_por_dia: 20` (`# [VALIDAR]` límite de la cuenta y del número).
    - `plantilla: {nombre, idioma: es, version}` (`# [VALIDAR]` aprobada por Meta).
    - `codigos_baja: [131050]` (`# [VALIDAR]` códigos de Meta que significan "el usuario no quiere recibir marketing").
- **`CanalContacto` (007):**
  - **Modo:** suma `modo: Literal['pull', 'push']`. `smtp_email` es `pull` e implementa `leer_respuestas()`. `whatsapp_meta` es `push` e implementa `verificar` + `parsear`. Así ningún adaptador implementa un método vacío que mienta en la suite de contrato.
  - **Errores:** suma `MensajeRechazado(CanalNoDisponible)` para un rechazo definitivo del proveedor (4xx). `CanalNoDisponible` sigue siendo el error indeterminado.
- **`clasificadores.*` con `usos: [respuestas]`** (007): sin cambios. Los mensajes entrantes de WhatsApp pasan por el mismo clasificador habilitado, fuera del webhook.
- **`RegistroCostos`**: tipo nuevo `whatsapp_plantilla`:
  - unidad mensaje, tarifa `whatsapp.usd_por_plantilla_co`;
  - `proveedor='meta'`, `lead_id` set, `canal='whatsapp'`, `fuente=NULL`, `gratis=false`.
- **`DarDeBaja`** (007):
  - suma `via='whatsapp'` y un `contacto_id` opcional, que queda en la entrada de `solicitudes` (`{tipo:'baja', via, contacto_id, ts}`);
  - los llamadores que conocen el contacto lo pasan: token de enlace y de mailto, respuesta, clasificador, webhook. Así la tasa de bloqueo sabe de qué canal vino la baja.
- **`RepositorioContactos`** (007): suma `elegibles_whatsapp()`, `registrar_opt_in(...)`, `contacto_por_message_id(...)` y `lead_whatsapp_por_telefono_hmac(...)`.
- Nada de `calificadores.*` ni `fuentes.*`: el slice no descubre ni califica.

## Skills que aplican
- `cumplimiento-datos`:
  - **regla 2:** WhatsApp exige opt-in registrado y la validación del dueño. Canal publicado no es opt-in, y opt-in no habilita un número no publicado.
  - **regla 3:** el número es el comercial de la empresa (`juridica`), nunca uno que dictó una persona.
  - **regla 5:** sin fila en `cumplimiento` o sin `base_legal`, no sale nada.
  - **regla 6:** opt-out por "BAJA" en todos los canales, con test.
  - **regla 7:** la plantilla pasa `plantilla.validar` versión WhatsApp:
    - identificación;
    - finalidad;
    - origen = "nos pidió que le escribiéramos por WhatsApp";
    - "responda BAJA";
    - enlace a `/privacidad`;
    - menos de 100 palabras, 1 pregunta, sin adjuntos.
  - **regla 8:** validación del dueño, ≤ M intentos por día, tasa de bloqueo < 1 %.
  - **regla 9:** el texto de respuesta va cifrado y ni el teléfono ni el texto aparecen nunca en logs.
- `libro-costos`: `whatsapp_plantilla` con `lead_id` y `canal`, escrita en el momento del intento. `costo_por_respuesta('whatsapp')` hecho a mano en el test.
- `fuentes-publicas`: el número sale de la fuente que ya lo publicó (sitio web u OSM), no de una fuente nueva. Nada de Facebook ni Instagram, aunque WhatsApp sea de Meta.
- `slice-tdd`.

## Evals
| Eval | Componente bajo prueba | Forma | Significado | Ground truth | Umbral | k |
|---|---|---|---|---|---|---|
| `clasificacion_respuestas` (007, se amplía) | el clasificador de `respuestas` sobre texto de WhatsApp | `clasificacion ∈ enum` | igual que en la 007 | 6 casos nuevos etiquetados a mano, con `canal: whatsapp`: "ok", "👍", "no gracias", "llámenme", "No sé, cuénteme más", uno con emojis | el de la 007, sin bajar | el de la 007 |

No hay eval nuevo. La plantilla es fija: no usa LLM y la cubre `plantilla.validar`, que es determinista. La baja también es determinista.

El clasificador ya tiene eval, pero su set es de emails, y el texto de WhatsApp es más corto y más ambiguo. Por eso el set suma 6 casos. Cambia el fingerprint del dataset y el baseline se regenera en el mismo PR, con la justificación (principio IX). Si la 007 dejó ese eval para la 012, los 6 casos se van con él.

## Flujo principal
1. **Gate al arrancar.** Con `whatsapp_meta.habilitado: true`, la app no arranca (`ConfigInvalida`) en cualquiera de estos casos:
   1. `validacion_dueno` es null;
   2. `whatsapp.usd_por_plantilla_co` es null ("tarifa pendiente");
   3. falta `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` o `WHATSAPP_TENANT_ID`. El error nombra la variable y no muestra ningún valor.

   Con `habilitado: false`, el adaptador no se carga. La ruta `/webhooks/whatsapp` existe igual y responde 404. Los endpoints de opt-in y de envío por WhatsApp responden 409 `{"regla": "canal_no_disponible"}`.
2. **Opt-in.** En **Respuestas** (007), una respuesta `interesado` de un lead muestra "Registrar opt-in de WhatsApp". `POST /respuestas/{id}/opt-in-whatsapp`, sin cuerpo:
   1. la respuesta tiene que ser `interesado` y del tenant (RLS). Si no → 422 `{"regla": "opt_in_requiere_interesado"}`;
   2. el lead tiene que tener `telefono_cifrado` con `telefono_canal ∈ {sitio_web, osm_contacto}`. Si no → 422 `{"regla": "opt_in_requiere_numero_comercial"}`;
   3. si el lead está en `v_leads_con_opt_out` → 409 `{"regla": "dado_de_baja"}`;
   4. se guarda en `opt_in_whatsapp` con `respuesta_id` y `registrado_por` (el usuario del JWT). No se copia el teléfono: se usa el del lead (minimización);
   5. un segundo opt-in del mismo lead → 409.
3. **Borrador.** `RedactarBorradoresWhatsapp` toma `v_elegibles_whatsapp` y crea un `contactos` con:
   - `canal='whatsapp'`, `redactor='plantilla_fija'` y `plantilla_version`;
   - el cuerpo renderizado con el nombre de la empresa del tenant.

   El cuerpo pasa `plantilla.validar(..., canal='whatsapp')`. Si no pasa, no se crea nada y se loguea el `lead_id`. El contacto queda en `pendiente_aprobacion`.
4. **Aprobación.** La misma de la 007 (`POST /contactos/{id}/aprobar`), pero sin edición del cuerpo: en WhatsApp el texto es el de la plantilla aprobada por Meta. Un `PATCH` del cuerpo de un contacto `whatsapp` → 422 `{"regla": "plantilla_fija"}`.
5. **Envío.** `EnviarAprobados` (007) atiende también `canal='whatsapp'`. Por cada fila:
   1. reclama la fila (`aprobado → enviando`, como en la 007);
   2. sin `cumplimiento` o sin `base_legal` → `SinBaseLegal`, y la fila pasa a `descartado`;
   3. re-chequea `v_contactables_whatsapp`. Si el lead salió (baja, fusión, revisión de dedup, ya no es `juridica`), la fila pasa a `descartado`;
   4. **freno:** si `frenado(bloqueos, entregados, tasa_bloqueo_max)` sobre `v_tasa_bloqueo['whatsapp']` da verdadero (`bloqueos / entregados ≥ max`, o algún bloqueo con 0 entregados), no sale **ningún** WhatsApp más:
      - la fila vuelve a `aprobado`;
      - se loguea una vez;
      - el tablero muestra el aviso.

      El freno no se reabre solo (`# ponytail: freno sin reapertura; botón con doble confirmación si un evento lo necesita`);
   5. **tope:** si las filas `whatsapp_plantilla` de hoy (America/Bogota) en `costos` llegan a `max_por_dia`, la fila vuelve a `aprobado` y sale mañana. Cuenta cada intento, haya salido o fallado: un rebote, una falla o una fila trabada en `enviando` no liberan cupo;
   6. descifra `leads.telefono_cifrado` solo dentro del caso de uso y llama a `enviar`;
   7. escribe `whatsapp_plantilla` en `costos` **antes de devolver**, también si el transporte falla: no sabemos si Meta cobró (mismo criterio que la 007). Después, según el resultado:
      - **ok:** guarda `message_id` (el `wamid`) y `enviado_en`;
      - **`MensajeRechazado` (4xx):** la fila pasa a `no_entregable`, sin reintento;
      - **`CanalNoDisponible` (timeout, 5xx, conexión):** la fila queda en `enviando` para que la revise un humano. No se reintenta sola, porque Meta pudo haber aceptado y un reintento le mandaría un segundo WhatsApp al lead (mismo `ponytail` que la 007 para filas trabadas).
6. **Webhook.**
   - `GET /webhooks/whatsapp` contesta el challenge de Meta si `hub.verify_token` coincide con `WHATSAPP_VERIFY_TOKEN` (`compare_digest`). Si no, 403.
   - `POST /webhooks/whatsapp`:
     1. si `Content-Length` pasa de 256 KB → 413. Si falta o miente, la lectura se corta al pasar 256 KB → 413, sin leer el resto;
     2. `verificar(cuerpo, headers)`: `X-Hub-Signature-256` = `sha256=` + HMAC-SHA256(`WHATSAPP_APP_SECRET`, cuerpo crudo), comparado con `compare_digest`. Si falta o no coincide → 401, sin efectos;
     3. JSON inválido → 400;
     4. si `metadata.phone_number_id` no es `WHATSAPP_PHONE_ID` → 200 sin efectos (Meta reintenta todo lo que no sea 200);
     5. abre la unidad de trabajo con `SET LOCAL app.tenant_id = WHATSAPP_TENANT_ID`;
     6. `parsear(cuerpo)` y, por cada evento:
        - **estado de un `wamid` que no está en `contactos`** (por ejemplo, después de un timeout): sin efectos;
        - **estado `failed`:** busca el contacto por `message_id` y lo pasa a `rebotado`. Si el código está en `codigos_baja` → `DarDeBaja(via='whatsapp', contacto_id)`;
        - **estados `delivered`, `read`:** `entregado_en = COALESCE(entregado_en, timestamp)`. Repetido no cambia nada;
        - **estado `sent`:** sin efecto (Meta aceptó, todavía no entregó);
        - **mensaje entrante:** `lead_whatsapp_por_telefono_hmac(hmac(from))` devuelve el lead con opt-in y un contacto `whatsapp` en `enviando`, `enviado` o `rebotado`. Son todos intentos con costo escrito: después de un timeout no hay `wamid`, pero Meta pudo haber entregado, y un BAJA tiene que registrarse igual. Si hay varios leads con ese `telefono_hmac`, gana el que tiene el contacto, y `v_elegibles_whatsapp` garantiza que hay uno solo. Si no hay ninguno, el mensaje se descarta sin guardar nada (minimización). Un mensaje entrante prueba la entrega: si el contacto no tiene `entregado_en`, se pone con el `timestamp` del mensaje (así un trabado que el lead contesta pasa a entregado).

          Si la primera línea normalizada es `BAJA`, `NO` o `STOP` → respuesta `pide_no_contacto` con `clasificador='determinista'`, y `DarDeBaja(via='whatsapp', contacto_id)`, sin LLM. Si no, la respuesta se guarda `sin_clasificar`, con el texto truncado a 10 KB y cifrado;
     7. idempotente por `wamid` (`respuestas.message_id UNIQUE`). El mismo estado dos veces no cambia nada;
     8. responde 200. **Nunca** manda un mensaje como respuesta automática.
7. **Clasificación fuera del webhook.** `ClasificarRespuestasPendientes` corre en la misma corrida programada que `EnviarAprobados`. Toma las respuestas `whatsapp` en `sin_clasificar` y aplica el orden de la 007 sin los pasos de email (DSN, `Auto-Submitted`, token). El texto va delimitado como hostil. `rechazo` y `pide_no_contacto` → `DarDeBaja(via='clasificador', contacto_id)`, como en la 007.

   Así el webhook contesta en milisegundos y un reintento de Meta no paga el LLM dos veces.
8. **Tablero.** `v_tablero_fuentes` y `v_costo_por_respuesta` ya van por canal: con contactos `whatsapp`, las columnas se llenan solas. Se suman `v_tasa_bloqueo` por canal y el aviso de freno.

## Terminado cuando (tests que hoy fallan)

**Gate** (`backend/tests/unit/test_config_whatsapp.py`)
- `::test_deshabilitado_no_carga_adaptador`: con `habilitado: false`, el registro no tiene `whatsapp_meta` y no se lee ninguna variable `WHATSAPP_*`.
- `::test_habilitado_sin_validacion_del_dueno_es_config_invalida`.
- `::test_habilitado_con_tarifa_null_es_config_invalida`: el mensaje dice "tarifa".
- `::test_habilitado_sin_variable_es_config_invalida[WHATSAPP_TOKEN|WHATSAPP_PHONE_ID|WHATSAPP_APP_SECRET|WHATSAPP_VERIFY_TOKEN|WHATSAPP_TENANT_ID]`: el error nombra la variable y no contiene el valor de ninguna de las otras.

**Plantilla** (`backend/tests/unit/test_plantilla.py`, se suma a la 007)
- `::test_plantilla_whatsapp_pasa_regla_7`: la plantilla de `config/plantillas/whatsapp_v1.txt`, renderizada con un nombre de empresa de 60 caracteres, pasa `validar(..., canal='whatsapp')`.
- `::test_plantilla_whatsapp_sin_baja_falla`: la misma plantilla sin "responda BAJA" → `regla='opt_out'`.
- `::test_plantilla_whatsapp_sin_origen_falla`: sin la frase de origen → `regla='origen'`.
- *Regresión, ya en verde:* los tests de `validar` para email de la 007, sin cambios.

**Freno** (`backend/tests/unit/test_freno.py`)
- `::test_borde`: `frenado(1, 100, 0.01) is True`, `frenado(1, 101, 0.01) is False`, `frenado(0, 0, 0.01) is False` (sin entregas ni bloqueos no hay tasa), `frenado(1, 0, 0.01) is True` (un bloqueo sin ninguna entrega frena).

**Opt-in** (`backend/tests/integration/test_opt_in_whatsapp.py`, sobre el fixture extendido de la 007: A `interesado` y C `rebote`, los dos con `telefono_canal='sitio_web'`)
- `::test_opt_in_de_interesado_se_guarda`: sobre la respuesta de A → 201, 1 fila con `respuesta_id` y `registrado_por`, sin columnas de teléfono.
- `::test_opt_in_de_respuesta_no_interesado_es_422`: sobre la respuesta `rebote` de C → `opt_in_requiere_interesado`, 0 filas.
- `::test_numero_no_comercial_es_422[whatsapp_osm|sin_telefono]`: A pasado por SQL a `telefono_canal='whatsapp_osm'`, o sin teléfono → `opt_in_requiere_numero_comercial`, 0 filas.
- `::test_lead_dado_de_baja_es_409`.
- `::test_segundo_opt_in_del_mismo_lead_es_409`.
- `::test_opt_in_con_canal_deshabilitado_es_409`: `canal_no_disponible`.

**Elegibles** (`backend/tests/integration/test_elegibles_whatsapp.py`, sobre el fixture extendido de la 007 más el opt-in de A)
- `::test_interesado_sin_opt_in_no_es_elegible`: sin opt-in, `v_elegibles_whatsapp` está vacía, aunque A sea `interesado` y tenga teléfono publicado.
- `::test_con_opt_in_es_elegible`: con el opt-in aparece A, y nadie más.
- `::test_natural_con_opt_in_no_es_elegible`: A pasado por SQL a `tipo_titular='natural'` → no aparece.
- `::test_baja_por_cualquier_canal_excluye[enlace|respuesta|clasificador]`: después de `DarDeBaja` con esa `via`, A no aparece.
- `::test_baja_de_otro_lead_con_el_mismo_telefono_excluye`: otro lead con el mismo `telefono_hmac` y dado de baja → A no aparece (lo hace `v_leads_con_opt_out` de la 007; queda como regresión).
- `::test_mismo_telefono_dos_leads_un_solo_contacto`: dos leads con el mismo `telefono_hmac`, los dos con opt-in → `RedactarBorradoresWhatsapp` crea 1 contacto.
- `::test_ya_contactado_por_whatsapp_no_vuelve`: con un contacto `whatsapp` de A en cualquier estado, A no aparece.

**Envío** (`backend/tests/integration/test_envio_whatsapp.py`, con `WhatsappMeta` sobre `httpx.MockTransport` y la tarifa de prueba `whatsapp.usd_por_plantilla_co = 0.30`)
- `::test_borrador_es_plantilla_fija_pendiente`: `redactor='plantilla_fija'`, `estado='pendiente_aprobacion'` y la `plantilla_version` de la config.
- `::test_editar_cuerpo_whatsapp_es_422`: `plantilla_fija`.
- `::test_sin_aprobacion_no_sale`: 0 requests al transporte.
- `::test_envio_escribe_costo_whatsapp_plantilla`: un contacto aprobado da:
  - 1 request con el nombre de plantilla de la config y el teléfono del lead;
  - `contactos.message_id` = el `wamid` falso;
  - 1 fila `whatsapp_plantilla` con el `lead_id` de A, `canal='whatsapp'`, `proveedor='meta'`, 0.30 y `gratis=false`.
- `::test_4xx_no_reintenta`: 400 → `no_entregable`, 1 fila de costo. Una segunda corrida da 0 requests.
- `::test_timeout_no_reenvia`: timeout → la fila queda en `enviando`, 1 fila de costo, sin `enviado_en`. Una segunda corrida da 0 requests. El mensaje de la excepción no contiene el teléfono.
- `::test_sin_base_legal_no_envia`: `base_legal` nula por SQL → `descartado`, 0 requests.
- `::test_reverifica_contactable_al_enviar`: aprobado y después dado de baja → `descartado`, 0 requests.
- `::test_tope_diario`: con `max_por_dia: 1` y 2 aprobados → 1 request, el otro sigue en `aprobado`.
- `::test_intento_fallido_ocupa_cupo`: con `max_por_dia: 1`, el primero da 400 → el segundo no sale hoy.
- `::test_intento_trabado_ocupa_cupo`: con `max_por_dia: 1`, el primero da timeout → el segundo no sale hoy.
- `::test_con_bloqueo_frena_el_siguiente`: 1 contacto `whatsapp` entregado con baja `via='whatsapp'` de ese contacto → 0 requests para el siguiente aprobado, que sigue en `aprobado`.
- `::test_sin_bloqueos_no_frena`: 1 entregado sin baja → sale.

**Webhook** (`backend/tests/integration/test_webhook_whatsapp.py`, con payloads de `backend/tests/fixtures/whatsapp/*.json`)
- `::test_verify_challenge_ok` y `::test_verify_token_incorrecto_es_403`.
- `::test_sin_firma_es_401` y `::test_firma_invalida_es_401`: 0 filas nuevas en `respuestas` y ningún cambio en `contactos`.
- `::test_json_invalido_con_firma_valida_es_400`.
- `::test_cuerpo_mayor_a_256kb_es_413_sin_leer_el_resto`: un stream de 1 MB sin `Content-Length` → 413, y el generador de prueba se consumió como mucho hasta 256 KB + un chunk.
- `::test_phone_number_id_desconocido_es_200_sin_efectos`.
- `::test_deshabilitado_es_404`.
- `::test_failed_pasa_a_rebotado`.
- `::test_failed_131050_da_de_baja_y_frena`: `opt_out_at` set, `solicitudes` suma `{via:'whatsapp', contacto_id}`, `v_tasa_bloqueo['whatsapp'].bloqueos = 1` con `entregados = 0`, y el siguiente aprobado no sale (`frenado(1, 0, …)`).
- `::test_delivered_marca_entregado[delivered|read]`: `entregado_en` queda con el `timestamp` del estado; un segundo `read` no lo cambia.
- `::test_sent_no_cambia_nada`.
- `::test_trabado_que_contesta_pasa_a_entregado`: contacto en `enviando` sin `wamid` + mensaje entrante de ese teléfono → `entregado_en` puesto y `v_tasa_bloqueo['whatsapp'].entregados = 1`.
- `::test_baja_en_primera_linea_da_de_baja_sin_llm[BAJA|baja |Stop|NO]`: respuesta `pide_no_contacto` con `clasificador='determinista'`; el clasificador falso registra 0 llamadas.
- `::test_texto_libre_queda_sin_clasificar`: con "No sé, cuénteme más" → respuesta `sin_clasificar` y 0 llamadas al clasificador. `respuesta_texto_cifrado` no contiene el texto en claro.
- `::test_remitente_sin_opt_in_se_descarta`: 200 y 0 filas nuevas.
- `::test_baja_tras_timeout_da_de_baja`: el contacto de A queda en `enviando` por un timeout, sin `wamid`. Entra un "BAJA" desde el teléfono de A → `opt_out_at` queda puesto y `solicitudes` suma `{via:'whatsapp', contacto_id}`.
- `::test_estado_de_wamid_desconocido_es_200_sin_efectos[sent|failed]`: un estado con un `wamid` que no está en `contactos` → 200 y ningún cambio en `contactos` ni en `solicitudes`.
- `::test_mismo_wamid_dos_veces_es_idempotente`: 1 respuesta.
- `::test_nunca_responde_automatico`: después de cada payload de la carpeta, 0 requests de envío al transporte.

**Clasificación** (`backend/tests/integration/test_clasificar_pendientes_whatsapp.py`)
- `::test_pendiente_whatsapp_va_al_clasificador`: un `sin_clasificar` de WhatsApp → 1 llamada al `ClasificadorFalso`, que devuelve `interesado`, y la respuesta queda `interesado`. Una segunda corrida da 0 llamadas.
- `::test_rechazo_por_whatsapp_da_de_baja_y_suma_bloqueo_whatsapp`: el falso devuelve `rechazo` → `DarDeBaja(via='clasificador', contacto_id)` y `v_tasa_bloqueo['whatsapp'].bloqueos = 1`.

**Contrato y arquitectura**
- `backend/tests/contratos/test_canal_contacto.py` (007) suma `whatsapp_meta` con `httpx.MockTransport`:
  - `enviar` devuelve un `message_id` y escribe su fila de costo;
  - un error de transporte es `CanalNoDisponible`, sin el teléfono en el mensaje;
  - `::test_cada_canal_cumple_su_modo`: un canal `pull` implementa `leer_respuestas`, un canal `push` implementa `verificar` y `parsear`, y ninguno implementa los dos.
- `test_api_auth.py::test_rutas_publicas_son_exactamente_estas`: la lista suma `/webhooks/whatsapp` (GET y POST), con el canal habilitado o no.
- `test_rls.py::test_tenant_b_no_accede_a[opt_in_whatsapp]` (la lista fija suma la tabla).
- `test_privilegios_supabase.py::test_anon_y_authenticated_sin_privilegios`: el assert previo exige `opt_in_whatsapp`, `v_contactables_whatsapp`, `v_elegibles_whatsapp` y `v_tasa_bloqueo`.
- `test_contacto_no_aparece_en_logs.py`: suma el teléfono de A en un envío por WhatsApp y el texto de un mensaje entrante por el webhook.
- `test_costos_por_adaptador.py`: un `WhatsappMeta.enviar` que no pasa por `RegistroCostos` falla.
- `test_import_linter.py`: `httpx` hacia la Graph API solo en `contacto/infraestructura/`. El contrato de fuentes prohibidas no se toca, porque WhatsApp no es fuente.
- `test_migraciones.py`:
  - `::test_migracion_0009_sobre_0008_con_datos`: con contactos `email` existentes, `upgrade` conserva todo, y `downgrade` falla si hay algún contacto `whatsapp` (no se pierde una traza en silencio);
  - `::test_check_canal_admite_whatsapp_y_rechaza_sms`.
- `test_baja.py` (007) suma `::test_baja_por_enlace_registra_contacto_id`: la entrada de `solicitudes` tiene el `contacto_id` del token.

**Tablero** (`backend/tests/integration/test_vistas_tablero.py`, se suma a la 007)

Corre sobre `fixture_whatsapp`. Parte del fixture extendido de la 007 (A `interesado` y C `rebote` por email, filas 7 y 8) y suma:
- el opt-in de A;
- un contacto `whatsapp` de A `enviado` y con `entregado_en`, con `whatsapp_plantilla` 0.30 y `gratis=false`;
- una respuesta `interesado` de A por WhatsApp.

Tests:
- `::test_costo_por_respuesta_whatsapp`:
  - `lista = 0.80`: A 0.20 de `v_prorrateo` + 0.30 de la fila 8 con `canal='whatsapp'` + 0.30 de la plantilla;
  - `real = 0.70`: 0.10 + 0.30 + 0.30;
  - divisor 1 lead → `0.80` / `0.70`.

  La fila 8 es de G, que no puede tener WhatsApp. Entra igual porque la vista suma todo `v_costos` con `canal='whatsapp'`, y eso es coherente con la definición de la 007.
- *Regresión, ya en verde:* `::test_costo_por_respuesta_email` sigue en `0.71` / `0.51`. A contestó por los dos canales y cuenta una vez en cada divisor, porque el divisor cuenta respuestas cuyo `contactos.canal` es ese canal.
- `::test_tasa_bloqueo_por_canal`:
  - `whatsapp`: `entregados=1`, `bloqueos=0`, `tasa=0` (el contacto de A del fixture tiene `entregado_en`);
  - después de un BAJA de A por WhatsApp: `bloqueos=1`, `tasa=1.0`;
  - `::test_rebote_no_entra_al_denominador`: se suma un contacto `whatsapp` `rebotado` sin baja → `entregados` sigue en 1 y `tasa` no cambia;
  - `::test_trabado_bloqueado_cuenta_como_bloqueo`: un contacto en `enviando` sin `entregado_en` con baja `via='whatsapp'` de ese contacto → `bloqueos` suma 1 y `entregados` no cambia;
  - una baja de A por el enlace del email suma al bloqueo de `email`, no al de `whatsapp`.
- *Regresión, ya en verde:* `::test_tablero_contactados_entregados_respondieron`.

**Front**
- `frontend/src/respuestas/Respuestas.test.tsx::registrar_opt_in_solo_en_interesado`: el botón aparece en `interesado` y no en otra clasificación, y el 422 `opt_in_requiere_numero_comercial` se muestra como texto.
- `frontend/src/mensajes/Mensajes.test.tsx::whatsapp_se_aprueba_sin_editar`: un contacto `whatsapp` muestra el cuerpo sin edición y el botón Aprobar.
- `frontend/src/tablero/Tablero.test.tsx::muestra_tasa_de_bloqueo_y_aviso_de_freno`: con `tasa ≥ 0.01` aparece el aviso "WhatsApp frenado: tasa de bloqueo 1 %".

**Evals**
- `uv run python -m evals.run` pasa con los 6 casos nuevos de `clasificacion_respuestas` y el baseline regenerado.

## Fuera del alcance
- **WhatsApp como primer toque.** Meta exige opt-in, y la regla 2 también: un número publicado no es opt-in.
- **Un número distinto al publicado** ("escríbanme al 300…"). Puede ser el celular de una persona (regla 3). `# ponytail: el humano contesta por email; si un evento lo pide, se suma con la validación del dueño`.
- **Conversación libre dentro de la ventana de 24 h.** Solo se manda la plantilla; lo que sigue lo atiende la pyme desde su WhatsApp Business. `# ponytail: sin bandeja de chat; entra si la pyme la pide`.
- **Redacción con LLM para WhatsApp.** La plantilla la aprueba Meta y no puede variar.
- **Baja solo de WhatsApp.** Un BAJA por WhatsApp da de baja en todos los canales, que es lo más conservador. `# [VALIDAR]` si el dueño quiere baja por canal.
- **Reintento automático y reapertura del freno.** Ver los pasos 5.4 y 5.7 del flujo.
- **Varios números o varios tenants con WhatsApp.** Un número por despliegue (`WHATSAPP_TENANT_ID`). `# ponytail: tabla de ruteo phone_number_id → tenant cuando haya un segundo tenant`.
- **Medios, botones, plantillas con imagen.** Solo texto.
- **Opt-in fuera de una respuesta** (formulario web, QR). Lo ve la 010 si llega.
- **Rate limiting del webhook.** 012.

## Decisiones técnicas
**Módulo** `backend/app/modulos/contacto/` (el de la 007):
- `dominio/`:
  - `opt_in.py`: `validar_opt_in(clasificacion, telefono_canal, dado_de_baja)`;
  - `freno.py`: `frenado(bloqueos, entregados, maximo) -> bool`;
  - `plantilla.validar` suma el parámetro `canal`.
- `aplicacion/`:
  - `registrar_opt_in.py`;
  - `redactar_borradores_whatsapp.py`;
  - `procesar_webhook_whatsapp.py`;
  - `clasificar_respuestas_pendientes.py`;
  - `enviar_aprobados.py` suma el freno, el tope y el mapeo de errores por canal.
- `infraestructura/`: `whatsapp_meta.py` (adaptador con `httpx`: `enviar`, `verificar`, `parsear`).
- La API (`/respuestas/{id}/opt-in-whatsapp`, `/webhooks/whatsapp`) vive en `backend/app/api/` y no importa nada de Meta.

**Opt-in = pedido del lead + número publicado.** `respuesta_id NOT NULL` es la prueba de que el lead pidió WhatsApp, y `registrado_por` guarda quién lo registró. El número es el que la empresa publicó, nunca uno nuevo. Así se cumplen a la vez Meta (opt-in), el PRD y `solo_numeros_comerciales_publicados` (número comercial publicado), y la regla 3 (nada nominal). `cumplimiento.base_legal` sigue siendo la del lead (007) y se exige igual.

**Tenant del webhook.** El webhook no trae un token nuestro. El tenant sale de `WHATSAPP_TENANT_ID` después de verificar la firma y el `phone_number_id`, y se fija con `SET LOCAL`, sin `SECURITY DEFINER` ni una tabla sin RLS. Los lookups (`message_id`, `telefono_hmac`) corren bajo la RLS de ese tenant.

**Firma sobre el cuerpo crudo.** El endpoint lee el cuerpo una sola vez, con tope, verifica con el adaptador y recién ahí parsea.

**Costo en el intento, sin reintento automático.** El costo se escribe aunque el transporte falle, porque no sabemos si Meta cobró. Como nada se reintenta solo, cada contacto tiene como mucho un costo por intento humano. `# [VALIDAR]` si Meta cobra por conversación o por mensaje: si cobra por conversación entregada, el costo pasa a escribirse con el `delivered`.

**Bloqueo por contacto, no por `via`.** La baja guarda el `contacto_id` que la originó, y `v_tasa_bloqueo` cuenta por el canal de ese contacto. Con `via` no alcanzaba: las bajas de email usan `enlace`/`mailto`/`respuesta`, y un `rechazo` por WhatsApp entra como `clasificador`.

**Tope y tasa miden cosas distintas** (decisión del dueño):
- **tope diario:** cuenta intentos. Trabados y rebotados ocupan cupo, porque cada uno escribió su costo;
- **tasa de bloqueo = bloqueos ÷ entregados**, no ÷ intentos. Un rebote no es una entrega y no entra al denominador. Entregado = `entregado_en` puesto por un `delivered`/`read` o por un mensaje entrante del lead;
- un trabado que después se confirma entregado (el lead contesta, o el humano que lo resuelve lo confirma) pasa al denominador. Si se confirma rechazado por bloqueo del destinatario (131050), entra por `DarDeBaja(via='whatsapp', contacto_id)` y cuenta como bloqueo;
- un `failed` 131050 es `rebotado` y bloqueo a la vez: suma al numerador y no al denominador. Por eso `frenado` recibe los conteos y no la tasa: con bloqueos > 0 y 0 entregados la tasa es nula y igual frena.

**Freno conservador.** Con n chico, una sola baja frena el canal. Es lo que pide la regla 8 (< 1 %) y lo que protege el número: Meta interviene arriba de 2–3 %.

**Variables de entorno nuevas** (Railway, servicio `api`): `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_TENANT_ID`. La cuenta de Meta es nueva para el evento, o la existente solo con la validación escrita del dueño, registrada en `docs/decisiones.md` y referenciada en `validacion_dueno` (constitución, reglas del proyecto).

**Migración `0009_whatsapp.py`** (a mano, revisada por un humano):

| Tabla / vista | Definición |
|---|---|
| `contactos` | `CHECK (canal IN ('email', 'whatsapp'))` reemplaza a `canal = 'email'`. `UNIQUE (tenant_id, lead_id, canal)` sigue. `+ entregado_en timestamptz NULL` (solo lo llena WhatsApp). |
| `opt_in_whatsapp` | `id`, `tenant_id`, `lead_id` FK, `respuesta_id` FK `respuestas` NOT NULL, `registrado_por` FK `usuarios`, `registrado_en`. `UNIQUE (tenant_id, lead_id)`. RLS por `tenant_id`. Sin columnas de contacto. |
| `respuestas` | Sin cambios de esquema: `message_id` guarda el `wamid`. Si la 007 fijó `solicitudes.via` con CHECK, se amplía con `whatsapp`. |
| `v_contactables_whatsapp` | opt-in ⋈ lead con: `juridica`; `telefono_cifrado` no nulo y `telefono_canal IN ('sitio_web', 'osm_contacto')`; `encaje ≠ no_encaja`; `fusionado_en IS NULL`; sin `revision_dedup` pendiente; con `cumplimiento` y `base_legal`; fuera de `v_leads_con_opt_out`. |
| `v_elegibles_whatsapp` | `v_contactables_whatsapp` sin contacto `whatsapp` previo del lead ni de otro lead con el mismo `telefono_hmac`. `DISTINCT ON (telefono_hmac)` por `registrado_en`. |
| `v_tasa_bloqueo` | Por `canal`: `entregados` = contactos con `entregado_en IS NOT NULL` (en `email`, `enviado − rebotado`, el mismo criterio de `v_tablero_fuentes` de la 007); `bloqueos` = contactos en `enviando`, `enviado` o `rebotado` cuyo `id` aparece como `contacto_id` en una entrada `tipo='baja'` de `solicitudes`; `tasa = bloqueos / NULLIF(entregados, 0)`. |

Todas las vistas con `security_invoker = true`. No redondean.

**Precisión de `v_costo_por_respuesta` (007):** el divisor cuenta leads distintos con una respuesta real cuyo `contactos.canal` es ese canal. El costo de descubrimiento de un lead entra en cada canal que lo contactó, así que `costo_por_respuesta` no se suma entre canales.

## Plan de tareas (TDD, en orden)
**Corte 1: gate, opt-in, envío, baja y freno (≈ 2 h 15)**
1. Rojo: `test_config_whatsapp.py` → verde con la carga del adaptador y `ConfigInvalida`.
2. Rojo: `test_migraciones.py` (0009) + `test_rls[opt_in_whatsapp]` + `test_privilegios_supabase` → verde con `0009_whatsapp.py`.
3. Rojo: `test_plantilla.py` (WhatsApp) + `test_freno.py` → verde con `config/plantillas/whatsapp_v1.txt`, `validar(canal=...)` y `frenado`.
4. Rojo: `test_opt_in_whatsapp.py` → verde con `RegistrarOptIn` y el endpoint.
5. Rojo: `test_elegibles_whatsapp.py` → verde con las vistas y `RedactarBorradoresWhatsapp`.
6. Rojo: `test_baja_por_enlace_registra_contacto_id` + `::test_tasa_bloqueo_por_canal` → verde con `contacto_id` en `DarDeBaja` y `v_tasa_bloqueo`.
7. Rojo: `test_canal_contacto.py[whatsapp_meta]` + `test_envio_whatsapp.py` + `test_costos_por_adaptador` → verde con `WhatsappMeta.enviar`, el freno, el tope y el mapeo de errores.
8. Rojo: `test_webhook_whatsapp.py` + `test_rutas_publicas_son_exactamente_estas` + `test_contacto_no_aparece_en_logs` → verde con `verificar`, `parsear` y `ProcesarWebhookWhatsapp`.

Cierre del corte 1, prueba manual con la cuenta del evento y un número de prueba de Meta (`# [VALIDAR]` sandbox):
1. registrar el opt-in;
2. aprobar el mensaje;
3. comprobar que llega la plantilla;
4. responder BAJA;
5. comprobar que el lead quedó dado de baja también en email y que el tablero muestra el freno.

**Corte 2: clasificación y tablero (≈ 45 min)**
9. Rojo: `test_clasificar_pendientes_whatsapp.py` → verde con `ClasificarRespuestasPendientes`.
10. Rojo: los 6 casos nuevos de `clasificacion_respuestas` → baseline regenerado, con la justificación en el PR.
11. Rojo: `::test_costo_por_respuesta_whatsapp` → verde (si la vista de la 007 no filtraba el divisor por `contactos.canal`, el arreglo va acá).

**Corte 3: front (≈ 30 min)**
12. Rojo: los tres tests del front → verde.
13. Doc:
    - `docs/arquitectura-backend.md`: el puerto `CanalContacto` con `modo`, el webhook y el freno;
    - `docs/arquitectura-frontend.md`;
    - README: variables `WHATSAPP_*` y "nace apagado".

**Orden de corte**, si no alcanza el tiempo (qué se corta y a dónde va):
1. **Corte 3:** el opt-in se registra por CLI y el tablero se lee por `GET /tablero`. El front pasa a la 012.
2. **Corte 2:** el texto libre queda `sin_clasificar` y un humano lo resuelve con la baja manual de la 007 (`POST /respuestas/{id}/baja`). Los casos del eval pasan a la 012.
3. **El corte 1 no se corta.**
   - Si el corte 1 no arranca antes de las **12:45 del domingo**, no se empieza. Con ≈ 2 h 15 no llega verde a las 3pm (PRD §9).
   - Si a las 3pm el corte 1 no está verde, se corta el slice entero: la rama no se mergea, `whatsapp_meta` queda en `habilitado: false` y el MVP es solo email.

## Riesgos
- **La validación del dueño o la tarifa no llegan:** el canal no se prende. Mitigación: todo el slice se prueba con `MockTransport`, y la demo muestra el gate (`canal_no_disponible`) como cumplimiento funcionando.
- **Meta tarda en aprobar la plantilla** (horas o días): sin plantilla aprobada no hay envío real. Mitigación: pedirla el sábado y, si no llega, usar el número de prueba de Meta en la demo. `# [VALIDAR]`.
- **Pocos leads con teléfono comercial publicado y opt-in:** el canal puede quedar con n = 0 o 1 en la demo. Es el resultado honesto del cumplimiento, y el tablero lo muestra como "sin dato".
- **El webhook no tiene el formato de los fixtures:** los payloads de `tests/fixtures/whatsapp/` salen de la doc de Meta (`# [VALIDAR]`) y se reemplazan por uno real en la prueba manual.
- **Códigos de baja equivocados:** un `failed` por otra causa daría de baja de más. Es el lado seguro del error, y se ajusta `codigos_baja` en la config.
- **Filas trabadas en `enviando` después de un timeout:** las resuelve un humano, igual que en la 007. Con el tope bajo son pocas.
- **El webhook público es superficie de ataque:** firma HMAC obligatoria, tope de tamaño sin leer el resto, `phone_number_id` verificado, idempotencia, cero respuestas automáticas y texto entrante tratado como hostil antes del LLM. El agente `security` lo revisa en el PR.
- **Cuándo cortar:** ver el orden de corte. Nunca se cortan el gate apagado por defecto, el opt-in ligado a una respuesta y al número publicado, la baja por WhatsApp en todos los canales, el freno y la firma del webhook.
