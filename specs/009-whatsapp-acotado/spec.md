# Spec 009 — WhatsApp acotado (whatsapp_asistido y whatsapp_meta)

**Slice:** 009 · **Rama:** `feature/009-whatsapp-acotado` · **Tiempo:** domingo, si hay tiempo (asistido ≈ 2 h 15; meta ≈ 3 h más) · **Carril:** @burbinagomez
**Depende de:** 002 (`cumplimiento`, `RegistroCostos`, unidad de trabajo con `SET LOCAL app.tenant_id`, `ConfigInvalida`), 003 (`leads.telefono_cifrado`/`telefono_hmac`/`telefono_canal`, cifrado con AAD), 005 (auth, `v_costos`, fixture A–J con las filas 7 `email` y 8 `whatsapp`), 006 (`tipo_titular`, `telefono_canal='sitio_web'` de A y C, `telefono_canal='whatsapp_comercial'`), 007 (`contactos`, `respuestas`, `plantilla.componer`/`validar`, `Redactor`, clasificación determinista, `AprobarMensaje`, `DarDeBaja`, `v_leads_con_opt_out`, `v_tablero_fuentes`, `v_costo_por_respuesta`, `clasificadores.sin_clasificar`, `RUTAS_PUBLICAS`, fixture extendido de Tablero). La 008 no es requisito. **Desbloquea:** 012 (pantalla de cumplimiento: opt-in y tasa de bloqueo), 013 (el pitch muestra "email → whatsapp (opt-in)" como segundo toque).

> WhatsApp **no** es primer toque frío: Meta exige opt-in y el contacto en frío "no está oficialmente permitido" (PRD §2b). Este slice abre WhatsApp con tres condiciones:
> - el lead **pidió** que le escriban por ahí en una respuesta al email: contestó `WHATSAPP`, o un humano lo registra desde una respuesta `interesado`;
> - el número es el **comercial que la empresa publicó** (PRD l.18, l.62, l.158);
> - el opt-in queda registrado y ligado a esa respuesta.
>
> Dos adaptadores detrás del mismo puerto `CanalContacto`:
> - **`whatsapp_asistido`** (`habilitado: true`): sin API de Meta ni cuenta. El sistema redacta con las reglas de la 007 y genera el enlace `wa.me` al WhatsApp comercial publicado (`telefono_canal='whatsapp_comercial'`). Un humano lo envía desde el teléfono de la pyme y marca "enviado". La respuesta se registra pegándola y pasa por el mismo clasificador. Costo: `minutos_humanos` por envío y por registro.
> - **`whatsapp_meta`** (`habilitado: false`): plantilla aprobada por Meta que cumple la regla 7 y se envía por la Cloud API. Se prende solo con la validación escrita del dueño, la tarifa cargada y las variables de entorno.
>
> Los dos comparten el opt-in, la aprobación humana por mensaje, el tope diario, el freno automático si la tasa de bloqueo llega al 1 % y la baja en todos los canales. WhatsApp se reporta siempre como **segundo toque con opt-in** ("email → whatsapp (opt-in)"), nunca comparado con el email como primer toque. Si el domingo 3pm el corte 1 (asistido) no está, se corta entero y el MVP es solo email (constitución, reglas del proyecto).

## Para quién
- **Pyme usuaria:** cuando un lead contesta el email con `WHATSAPP` (o con "escríbanme por WhatsApp", y ella lo registra con un clic), el sistema le deja listo un mensaje para el WhatsApp comercial de esa empresa. Con el asistido, lo aprueba, abre el enlace en su teléfono, aprieta enviar, marca "enviado" y después pega lo que le contesten. Sin cuenta de Meta y sin salirse de sus reglas.
- **Lead:** recibe WhatsApp solo si lo pidió y solo en el número que su empresa publicó. El mensaje viene identificado, con el porqué, de dónde salió el contacto y cómo salir ("responda BAJA"). Un BAJA por WhatsApp lo da de baja en todos los canales.
- **Jurado:** ve en el tablero la fila "email → whatsapp (opt-in)" aparte de "email": contactados, entregados, bloqueos, tasa de bloqueo y costo por respuesta, que suma el costo del lead completo (descubrimiento + email + WhatsApp), calculados desde `costos`.

## Qué hace
**Común a los dos adaptadores**
1. El email de la 007 suma la línea "Si prefiere seguir por WhatsApp, responda WHATSAPP." cuando el lead tiene `telefono_canal='whatsapp_comercial'` y `whatsapp_asistido` está habilitado. No es una pregunta: la plantilla sigue con una sola (regla 7).
2. Registra un opt-in de WhatsApp ligado a una respuesta del lead, sobre el teléfono comercial publicado del lead. El humano no tipea ningún número. Hay dos vías:
   - **palabra clave:** la primera línea de la respuesta al email es `WHATSAPP`. Es determinista, sin LLM;
   - **humano:** un botón sobre una respuesta `interesado`.
3. Suma WhatsApp al tablero como "email → whatsapp (opt-in)": tasa de bloqueo por canal y `costo_por_respuesta('whatsapp')`, que deja de ser NULL e incluye el email del mismo lead.

**`whatsapp_asistido`** (`habilitado: true`)

4. Redacta el mensaje con el `Redactor` de la 007, lo valida con la regla 7 (versión WhatsApp) y lo deja en `pendiente_aprobacion`. El humano puede editarlo, y se revalida.
5. Con el mensaje aprobado, emite un enlace `wa.me` con el número y el texto. Sin aprobación no hay enlace. El enlace no se guarda ni se loguea.
6. El humano envía desde el teléfono de la pyme y marca `enviado`, `no_entregable` o `descartado`. Cada envío marcado escribe `minutos_humanos` en `costos`.
7. El humano pega la respuesta del lead. Escribe `minutos_humanos`, y un BAJA da de baja en todos los canales sin LLM. El resto queda `sin_clasificar` para el clasificador.

**`whatsapp_meta`** (`habilitado: false`)

8. Arma el mensaje desde una plantilla fija aprobada por Meta, lo valida con la regla 7 (versión WhatsApp) y lo deja en `pendiente_aprobacion` para un humano, como en la 007.
9. Envía los aprobados por la Cloud API de Meta, con tope diario de intentos y freno por tasa de bloqueo. Escribe `whatsapp_plantilla` en `costos` por cada intento. Nunca reenvía solo.
10. Recibe el webhook de Meta firmado, con estados de entrega y mensajes entrantes:
    - un BAJA da de baja sin LLM;
    - un bloqueo de Meta da de baja y cuenta para el freno;
    - el resto se guarda `sin_clasificar` y se clasifica fuera del webhook;
    - nunca responde solo.

## Puertos y adaptadores que toca (`config/fuentes.yaml`)
- **`canales_contacto.whatsapp_asistido`** (`habilitado: true`): adaptador nuevo detrás del puerto **`CanalContacto`** de la 007. Sin red, sin cuenta y sin variables de entorno.
  - **Método:** `enlace(telefono_e164, cuerpo) -> str`, que arma `https://wa.me/<E.164 sin +>?text=<cuerpo url-encoded>`. Es una función pura: no envía nada.
  - **Config nueva:**
    - `solo_numeros_comerciales_publicados: true`: el número es `leads.telefono_cifrado` con `telefono_canal='whatsapp_comercial'`, el enlace de WhatsApp que la empresa publicó en su sitio (006);
    - `max_por_dia: 20` (`# [VALIDAR]` cuántos manda a mano una pyme sin que WhatsApp marque el número);
    - `minutos_por_envio: 1` y `minutos_por_registro: 1` (`# [VALIDAR]` medido en la prueba manual);
    - `tasa_bloqueo_max: 0.01`.
- **`canales_contacto.whatsapp_meta`** (`habilitado: false` hasta la validación escrita del dueño): adaptador nuevo detrás del puerto **`CanalContacto`** de la 007.
  - **Métodos:**
    - `enviar(mensaje) -> message_id`: manda la plantilla por `httpx` a la Graph API (`# [VALIDAR]` versión y forma del payload);
    - `verificar(cuerpo: bytes, headers) -> bool`: firma de Meta;
    - `parsear(cuerpo: bytes) -> list[MensajeEntrante | EstadoEntrega]`.

    La API no conoce a Meta: llama a `verificar` y a `parsear` del adaptador.
  - **Config que ya existe y este slice hace cumplir:**
    - `solo_numeros_comerciales_publicados: true`: el número es `leads.telefono_cifrado` con `telefono_canal ∈ {sitio_web, osm_contacto, whatsapp_comercial}`. `whatsapp_osm` queda fuera en los dos adaptadores porque puede ser el celular personal del tendero (003).
    - `tasa_bloqueo_max: 0.01`.
  - **Config nueva:**
    - `validacion_dueno: null`: fecha y referencia de la validación escrita en `docs/decisiones.md`. Con `habilitado: true` y `null`, la app no arranca.
    - `max_por_dia: 20` (`# [VALIDAR]` límite de la cuenta y del número).
    - `plantilla: {nombre, idioma: es, version}` (`# [VALIDAR]` aprobada por Meta).
    - `codigos_baja: [131050]` (`# [VALIDAR]` códigos de Meta que significan "el usuario no quiere recibir marketing").
- **`CanalContacto` (007):**
  - **Modo:** suma `modo: Literal['pull', 'push', 'manual']`. `smtp_email` es `pull` e implementa `leer_respuestas()`. `whatsapp_meta` es `push` e implementa `verificar` + `parsear`. `whatsapp_asistido` es `manual` e implementa solo `enlace`: lo envía un humano y la respuesta entra pegada. Así ningún adaptador implementa un método vacío que mienta en la suite de contrato.
  - **Errores:** suma `MensajeRechazado(CanalNoDisponible)` para un rechazo definitivo del proveedor (4xx). `CanalNoDisponible` sigue siendo el error indeterminado.
- **`clasificadores.*` con `usos: [respuestas]`** (007): sin cambios. Los mensajes entrantes de WhatsApp pasan por el mismo clasificador habilitado, fuera del webhook.
- **`RegistroCostos`**:
  - tipo nuevo `whatsapp_plantilla` (meta): unidad mensaje, tarifa `whatsapp.usd_por_plantilla_co`; `proveedor='meta'`, `lead_id` set, `canal='whatsapp'`, `fuente=NULL`, `gratis=false`;
  - tipo existente `minutos_humanos` (asistido, libro-costos): unidad minutos, tarifa `humano.usd_por_minuto` (0.25). Una fila por envío marcado (`minutos_por_envio`) y otra por respuesta pegada (`minutos_por_registro`), con `proveedor='humano'`, `lead_id` set, `canal='whatsapp'`, `fuente=NULL`, `gratis=false`.
- **`DarDeBaja`** (007):
  - suma `via='whatsapp'` y un `contacto_id` opcional, que queda en la entrada de `solicitudes` (`{tipo:'baja', via, contacto_id, ts}`);
  - los llamadores que conocen el contacto lo pasan: token de enlace y de mailto, respuesta, clasificador, webhook, respuesta pegada. Así la tasa de bloqueo sabe de qué canal vino la baja.
- **Clasificación determinista** (007): el orden en email pasa a ser DSN → `Auto-Submitted` → BAJA/NO → **`WHATSAPP`** → LLM. `WHATSAPP` en la primera línea normalizada da `interesado` con `clasificador='determinista'` y registra el opt-in por palabra clave. Solo en el canal `email`; BAJA gana siempre.
- **`plantilla.componer`** (007): suma la línea de WhatsApp en el email bajo las dos condiciones del paso 1 de Qué hace.
- **`RepositorioContactos`** (007): suma `elegibles_whatsapp(adaptador)`, `registrar_opt_in(...)`, `contacto_por_message_id(...)`, `lead_whatsapp_por_telefono_hmac(...)`, `emitir_enlace(...)` y `marcar(...)`.
- Nada de `calificadores.*` ni `fuentes.*`: el slice no descubre ni califica.

## Skills que aplican
- `cumplimiento-datos`:
  - **regla 2:** WhatsApp exige opt-in registrado y la validación del dueño. Canal publicado no es opt-in, y opt-in no habilita un número no publicado. Vale igual para los dos adaptadores: el asistido no relaja nada. La validación del dueño es sobre la cuenta o el proveedor de API (constitución:57); el asistido no usa ninguna, y por eso nace `habilitado: true` (ver Decisiones).
  - **regla 3:** el número es el comercial de la empresa (`juridica`), nunca uno que dictó una persona.
  - **regla 5:** sin fila en `cumplimiento` o sin `base_legal`, no sale nada.
  - **regla 6:** opt-out por "BAJA" en todos los canales, con test.
  - **regla 7:** la línea "Si prefiere seguir por WhatsApp, responda WHATSAPP." no es pregunta, así que el email sigue con 1. El mensaje de WhatsApp (plantilla de meta o borrador del asistido) pasa `plantilla.validar` versión WhatsApp:
    - identificación;
    - finalidad;
    - origen = "nos pidió que le escribiéramos por WhatsApp" + de dónde salió el número ("al WhatsApp publicado en su sitio web" o "en OpenStreetMap", según `telefono_canal`);
    - "responda BAJA";
    - enlace a `/privacidad`;
    - menos de 100 palabras, 1 pregunta, sin adjuntos.
  - **regla 8:** validación del dueño (meta), ≤ M intentos por día y tasa de bloqueo < 1 % (los dos).
  - **regla 9:** el texto de respuesta va cifrado y ni el teléfono, ni el texto, ni el enlace `wa.me` (que lleva los dos) aparecen nunca en logs.
- `libro-costos`: `whatsapp_plantilla` con `lead_id` y `canal`, escrita en el momento del intento; `minutos_humanos` por envío marcado y por respuesta pegada. `costo_por_respuesta('whatsapp')` hecho a mano en el test, sumando el email del mismo lead.
- `fuentes-publicas`: el número sale de la fuente que ya lo publicó (el sitio web para el asistido; sitio web u OSM para meta), no de una fuente nueva. Nada de Facebook ni Instagram, aunque WhatsApp sea de Meta.
- `slice-tdd`.

## Evals
| Eval | Componente bajo prueba | Forma | Significado | Ground truth | Umbral | k |
|---|---|---|---|---|---|---|
| `clasificacion_respuestas` (007, se amplía) | el clasificador de `respuestas` sobre texto de WhatsApp | `clasificacion ∈ enum` | igual que en la 007 | 6 casos nuevos etiquetados a mano, con `canal: whatsapp`: "ok", "👍", "no gracias", "llámenme", "No sé, cuénteme más", uno con emojis | el de la 007, sin bajar | el de la 007 |

No hay eval nuevo. La plantilla de meta es fija: no usa LLM y la cubre `plantilla.validar`, que es determinista. El borrador del asistido usa el `Redactor` de la 007, que ya tiene su eval, y pasa por el mismo `validar`. La baja y el `WHATSAPP` también son deterministas. Las respuestas pegadas son texto de WhatsApp: las cubren los mismos 6 casos.

El clasificador ya tiene eval, pero su set es de emails, y el texto de WhatsApp es más corto y más ambiguo. Por eso el set suma 6 casos. Cambia el fingerprint del dataset y el baseline se regenera en el mismo PR, con la justificación (principio IX). Si la 007 dejó ese eval para la 012, los 6 casos se van con él.

## Flujo principal
1. **Gate al arrancar.** Con `whatsapp_meta.habilitado: true`, la app no arranca (`ConfigInvalida`) en cualquiera de estos casos:
   1. `validacion_dueno` es null;
   2. `whatsapp.usd_por_plantilla_co` es null ("tarifa pendiente");
   3. falta `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` o `WHATSAPP_TENANT_ID`. El error nombra la variable y no muestra ningún valor.

   Con `whatsapp_meta.habilitado: false`, el adaptador no se carga y la ruta `/webhooks/whatsapp` existe igual y responde 404. Con `whatsapp_asistido.habilitado: false`, los endpoints de enlace, marcado y respuesta pegada responden 409 `{"regla": "canal_no_disponible"}`. El opt-in responde 409 `canal_no_disponible` solo si no hay **ningún** adaptador WhatsApp habilitado. `whatsapp_asistido` no tiene gate: no lleva secretos ni tarifa nueva (`humano.usd_por_minuto` ya existe).
2. **Línea en el email.** `plantilla.componer` (007) suma, antes del pie, "Si prefiere seguir por WhatsApp, responda WHATSAPP." solo si `whatsapp_asistido.habilitado` y el lead tiene `telefono_canal='whatsapp_comercial'`. El email sigue pasando `validar(..., canal='email')`, con 1 pregunta.
3. **Opt-in.** Los canales admitidos son la unión de los de cada adaptador WhatsApp habilitado: `whatsapp_comercial` para el asistido; `sitio_web`, `osm_contacto` y `whatsapp_comercial` para meta. Con el YAML real (asistido ON, meta OFF) es solo `whatsapp_comercial`. `validar_opt_in(clasificacion, telefono_canal, admitidos, dado_de_baja)` decide en las dos vías.
   1. **Palabra clave.** Una respuesta al email cuya primera línea normalizada (sin espacios, sin puntuación final, en mayúsculas) es `WHATSAPP` se clasifica `interesado` con `clasificador='determinista'`, sin LLM. Va después de DSN, `Auto-Submitted` y BAJA/NO: si la primera línea es BAJA, gana la baja. Si `validar_opt_in` pasa, se guarda en `opt_in_whatsapp` con `via='palabra_clave'`, `respuesta_id` y `registrado_por` NULL. Si no pasa (número no admitido, dado de baja, ya tenía opt-in), la respuesta queda `interesado` sin opt-in y no hay error: el lead igual dijo que le interesa. Solo aplica a respuestas del canal `email`.
   2. **Humano.** En **Respuestas** (007), una respuesta `interesado` de un lead muestra "Registrar opt-in de WhatsApp". `POST /respuestas/{id}/opt-in-whatsapp`, sin cuerpo:
      1. la respuesta tiene que ser `interesado` y del tenant (RLS). Si no → 422 `{"regla": "opt_in_requiere_interesado"}`;
      2. el lead tiene que tener `telefono_cifrado` con `telefono_canal` en los admitidos. Si no → 422 `{"regla": "opt_in_requiere_numero_comercial"}`;
      3. si el lead está en `v_leads_con_opt_out` → 409 `{"regla": "dado_de_baja"}`;
      4. se guarda en `opt_in_whatsapp` con `via='humano'`, `respuesta_id` y `registrado_por` (el usuario del JWT);
      5. un segundo opt-in del mismo lead → 409.

   En las dos vías no se copia el teléfono: se usa el del lead (minimización).
4. **Asistido** (`whatsapp_asistido`).
   1. **Borrador.** `RedactarBorradoresWhatsapp(adaptador='whatsapp_asistido')` toma `v_elegibles_whatsapp_asistido` y crea un `contactos` con `canal='whatsapp'`, `adaptador='whatsapp_asistido'` y el cuerpo del `Redactor` de la 007 (`claude_mensaje` o `plantilla_fija`, el que esté habilitado), con origen "nos pidió que le escribiéramos por WhatsApp". El cuerpo pasa `validar(..., canal='whatsapp')`; si no pasa, no se crea nada y se loguea el `lead_id`. Queda en `pendiente_aprobacion`.
   2. **Aprobación.** La de la 007: el humano edita el cuerpo y aprueba en el mismo `POST /contactos/{id}/aprobar` con cuerpo (no hay `PATCH`). Se revalida con `canal='whatsapp'` y solo se acepta en `pendiente_aprobacion`: aprobado el texto, no cambia.
   3. **Enlace.** `POST /contactos/{id}/enlace-whatsapp`, sin cuerpo:
      1. el contacto es del tenant (si no, 404), de `adaptador='whatsapp_asistido'` y está en `aprobado` o `enviando`. En cualquier otro estado → 409 `{"regla": "requiere_aprobacion"}` y no hay enlace;
      2. si está en `enviando`, devuelve el mismo enlace, sin tocar cupo ni costo (el humano cerró la pestaña);
      3. si está en `aprobado`: sin `cumplimiento` o sin `base_legal`, o fuera de `v_contactables_whatsapp` → el contacto pasa a `descartado` y 409 `{"regla": "no_contactable"}`. Con el freno activo → 409 `{"regla": "freno_whatsapp"}` y sigue `aprobado`. Si los `enlace_emitido_en` de hoy (America/Bogota) del asistido llegan a `max_por_dia` → 409 `{"regla": "tope_diario"}` y sigue `aprobado`;
      4. pasa a `enviando`, pone `enlace_emitido_en` y responde `{"enlace": "https://wa.me/…"}` con `Cache-Control: no-store`. El teléfono se descifra solo dentro del caso de uso; el enlace no se guarda ni se loguea.
   4. **Marcado.** `POST /contactos/{id}/marcar` con `{"resultado": "enviado" | "no_entregable" | "descartado"}`, solo desde `enviando` del asistido (si no → 409 `{"regla": "estado_invalido"}`, también al marcar dos veces):
      - `enviado`: pone `enviado_en` y `entregado_en` (lo envió un humano a un número que existe) y escribe `minutos_humanos` × `minutos_por_envio`;
      - `no_entregable`: el número no tiene WhatsApp o no salió. Escribe `minutos_humanos` (el humano lo intentó);
      - `descartado`: el humano se arrepintió antes de enviar. Sin costo.
   5. **Respuesta pegada.** `POST /contactos/{id}/respuesta-pegada` con `{"texto": "…"}`, solo sobre un contacto `enviado` del asistido (si no → 409 `{"regla": "estado_invalido"}`; texto vacío → 422):
      1. trunca a 10 KB y cifra el texto. `message_id = 'pegada:' + hmac(contacto_id + texto)`: pegar dos veces lo mismo no crea otra respuesta ni otro costo;
      2. escribe `minutos_humanos` × `minutos_por_registro` por cada respuesta nueva;
      3. si la primera línea normalizada es `BAJA`, `NO` o `STOP` → `pide_no_contacto` con `clasificador='determinista'` y `DarDeBaja(via='whatsapp', contacto_id)`, sin LLM. Si no, queda `sin_clasificar` y la toma `ClasificarRespuestasPendientes` (paso 9).
5. **Borrador meta.** Con los dos adaptadores habilitados, el asistido toma los leads con `whatsapp_comercial` y meta el resto (`# ponytail: reparto fijo por canal publicado; prioridad configurable si un evento lo pide`). `RedactarBorradoresWhatsapp(adaptador='whatsapp_meta')` toma `v_elegibles_whatsapp` (sin los `whatsapp_comercial` si el asistido está habilitado) y crea un `contactos` con:
   - `canal='whatsapp'`, `adaptador='whatsapp_meta'`, `redactor='plantilla_fija'` y `plantilla_version`;
   - el cuerpo renderizado con el nombre de la empresa del tenant.

   El cuerpo pasa `plantilla.validar(..., canal='whatsapp')`. Si no pasa, no se crea nada y se loguea el `lead_id`. El contacto queda en `pendiente_aprobacion`.
6. **Aprobación meta.** La misma de la 007 (`POST /contactos/{id}/aprobar`), pero sin edición del cuerpo: el texto es el de la plantilla aprobada por Meta. Un `POST /contactos/{id}/aprobar` con cuerpo editado sobre un contacto de `whatsapp_meta` → 422 `{"regla": "plantilla_fija"}`. La procedencia del número (sitio web u OpenStreetMap) va como variable de la plantilla que se somete a Meta.
7. **Envío meta.** `EnviarAprobados` (007) atiende también `adaptador='whatsapp_meta'`; los del asistido no los toca nunca. Por cada fila:
   1. reclama la fila (`aprobado → enviando`, como en la 007);
   2. sin `cumplimiento` o sin `base_legal` → `SinBaseLegal`, y la fila pasa a `descartado`;
   3. re-chequea `v_contactables_whatsapp`. Si el lead salió (baja, fusión, revisión de dedup, ya no es `juridica`), la fila pasa a `descartado`;
   4. **freno:** si `frenado(bloqueos, entregados, tasa_bloqueo_max)` sobre `v_tasa_bloqueo['whatsapp']` da verdadero (`bloqueos / entregados ≥ max`, o algún bloqueo con 0 entregados), no sale **ningún** WhatsApp más:
      - la fila vuelve a `aprobado`;
      - se loguea una vez;
      - el tablero muestra el aviso.

      El freno no se reabre solo (`# ponytail: freno sin reapertura; botón con doble confirmación si un evento lo necesita`);
   5. **tope** (propio de meta; el asistido tiene el suyo): si las filas `whatsapp_plantilla` de hoy (America/Bogota) en `costos` llegan a `max_por_dia`, la fila vuelve a `aprobado` y sale mañana. Cuenta cada intento, haya salido o fallado: un rebote, una falla o una fila trabada en `enviando` no liberan cupo;
   6. descifra `leads.telefono_cifrado` solo dentro del caso de uso y llama a `enviar`;
   7. escribe `whatsapp_plantilla` en `costos` **antes de devolver**, también si el transporte falla: no sabemos si Meta cobró (mismo criterio que la 007). Después, según el resultado:
      - **ok:** guarda `message_id` (el `wamid`) y `enviado_en`;
      - **`MensajeRechazado` (4xx):** la fila pasa a `no_entregable`, sin reintento;
      - **`CanalNoDisponible` (timeout, 5xx, conexión):** la fila queda en `enviando` para que la revise un humano. No se reintenta sola, porque Meta pudo haber aceptado y un reintento le mandaría un segundo WhatsApp al lead (mismo `ponytail` que la 007 para filas trabadas).
8. **Webhook meta.**
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
9. **Clasificación fuera del webhook.** `ClasificarRespuestasPendientes` corre en la misma corrida programada que `EnviarAprobados`. Toma las respuestas `whatsapp` en `sin_clasificar` (del webhook o pegadas) y aplica el orden de la 007 sin los pasos de email (DSN, `Auto-Submitted`, token, `WHATSAPP`). El texto va delimitado como hostil. `rechazo` y `pide_no_contacto` → `DarDeBaja(via='clasificador', contacto_id)`, como en la 007.

   Así el webhook contesta en milisegundos y un reintento de Meta no paga el LLM dos veces.
10. **Tablero.** `v_tablero_fuentes` y `v_costo_por_respuesta` ya van por canal: con contactos `whatsapp`, las columnas se llenan solas. La fila `whatsapp` se rotula "email → whatsapp (opt-in)", y su costo por respuesta suma también el costo `email` de esos mismos leads: un WhatsApp con opt-in siempre vino después de un email, y compararlo solo con su costo propio lo haría parecer más barato que el primer toque. Se suman `v_tasa_bloqueo` por canal y el aviso de freno. Los dos adaptadores caen en la misma fila: el canal es uno.

## Terminado cuando (tests que hoy fallan)

**Gate** (`backend/tests/unit/test_config_whatsapp.py`)
- `::test_deshabilitado_no_carga_adaptador`: con `habilitado: false`, el registro no tiene `whatsapp_meta` y no se lee ninguna variable `WHATSAPP_*`.
- `::test_habilitado_sin_validacion_del_dueno_es_config_invalida`.
- `::test_habilitado_con_tarifa_null_es_config_invalida`: el mensaje dice "tarifa".
- `::test_habilitado_sin_variable_es_config_invalida[WHATSAPP_TOKEN|WHATSAPP_PHONE_ID|WHATSAPP_APP_SECRET|WHATSAPP_VERIFY_TOKEN|WHATSAPP_TENANT_ID]`: el error nombra la variable y no contiene el valor de ninguna de las otras.
- `::test_yaml_real_asistido_on_meta_off`: el `config/fuentes.yaml` real carga sin error, con `whatsapp_asistido` en el registro y `whatsapp_meta` fuera, sin leer ninguna variable `WHATSAPP_*`.
- `::test_asistido_deshabilitado_endpoints_409[enlace-whatsapp|marcar|respuesta-pegada]`: con `whatsapp_asistido.habilitado: false` → `canal_no_disponible`, 0 cambios en `contactos` y 0 filas en `costos`.

**Plantilla** (`backend/tests/unit/test_plantilla.py`, se suma a la 007)
- `::test_plantilla_whatsapp_pasa_regla_7`: la plantilla de `config/plantillas/whatsapp_v1.txt`, renderizada con un nombre de empresa de 60 caracteres, pasa `validar(..., canal='whatsapp')`.
- `::test_plantilla_whatsapp_sin_baja_falla`: la misma plantilla sin "responda BAJA" → `regla='opt_out'`.
- `::test_plantilla_whatsapp_sin_origen_falla[sin_pedido|sin_procedencia_del_numero]`: falta cualquiera de las dos partes del origen → `regla='origen'`.
- `::test_email_con_whatsapp_comercial_suma_la_linea`: lead con `telefono_canal='whatsapp_comercial'` y asistido habilitado → el cuerpo contiene "responda WHATSAPP", sigue con 1 signo de pregunta y pasa `validar(..., canal='email')`.
- `::test_email_sin_whatsapp_comercial_no_la_suma[sitio_web|asistido_deshabilitado]`: sin la línea.
- `::test_borrador_asistido_pasa_regla_7`: el `Redactor` falso de la 007 con origen WhatsApp → pasa `validar(..., canal='whatsapp')`; sin "responda BAJA" → `regla='opt_out'`.
- *Regresión, ya en verde:* los tests de `validar` para email de la 007 y `::test_plantilla_fija_siempre_valida`, sin cambios.

**Freno** (`backend/tests/unit/test_freno.py`)
- `::test_borde`: `frenado(1, 100, 0.01) is True`, `frenado(1, 101, 0.01) is False`, `frenado(0, 0, 0.01) is False` (sin entregas ni bloqueos no hay tasa), `frenado(1, 0, 0.01) is True` (un bloqueo sin ninguna entrega frena).

**Opt-in** (`backend/tests/integration/test_opt_in_whatsapp.py`, sobre el fixture extendido de la 007: A `interesado` y C `rebote`, los dos con `telefono_canal='sitio_web'`; config de prueba con los dos adaptadores habilitados salvo que el test diga otra cosa)
- `::test_opt_in_de_interesado_se_guarda`: sobre la respuesta de A → 201, 1 fila con `via='humano'`, `respuesta_id` y `registrado_por`, sin columnas de teléfono.
- `::test_opt_in_de_respuesta_no_interesado_es_422`: sobre la respuesta `rebote` de C → `opt_in_requiere_interesado`, 0 filas.
- `::test_numero_no_comercial_es_422[whatsapp_osm|sin_telefono]`: A pasado por SQL a `telefono_canal='whatsapp_osm'`, o sin teléfono → `opt_in_requiere_numero_comercial`, 0 filas.
- `::test_admitidos_dependen_de_los_adaptadores`: con solo el asistido habilitado, A con `sitio_web` → 422 `opt_in_requiere_numero_comercial`; A pasado a `whatsapp_comercial` → 201.
- `::test_lead_dado_de_baja_es_409`.
- `::test_segundo_opt_in_del_mismo_lead_es_409`.
- `::test_opt_in_con_canal_deshabilitado_es_409`: con los dos adaptadores deshabilitados → `canal_no_disponible`.

**Opt-in por palabra clave** (`backend/tests/integration/test_opt_in_palabra_clave.py`, A pasado por SQL a `whatsapp_comercial`, con una respuesta nueva al email de A y el YAML real)
- `::test_responde_whatsapp_registra_opt_in[WHATSAPP|whatsapp|WhatsApp.|  Whatsapp ]`: respuesta `interesado` con `clasificador='determinista'`, 0 llamadas al clasificador falso y 1 fila en `opt_in_whatsapp` con `via='palabra_clave'`, `registrado_por` NULL y el `respuesta_id` de esa respuesta.
- `::test_whatsapp_de_lead_sin_numero_comercial_es_interesado_sin_opt_in`: A con `sitio_web` → `interesado`, 0 filas en `opt_in_whatsapp`.
- `::test_baja_gana_a_whatsapp`: primera línea "BAJA" y segunda "WHATSAPP" → `pide_no_contacto`, 0 filas en `opt_in_whatsapp`.
- `::test_whatsapp_de_dado_de_baja_no_registra`: A en `v_leads_con_opt_out` → 0 filas en `opt_in_whatsapp`.
- `::test_whatsapp_en_otra_linea_va_al_llm`: "Hola, ¿tienen WHATSAPP?" → 1 llamada al clasificador falso y 0 filas en `opt_in_whatsapp`.

**Elegibles** (`backend/tests/integration/test_elegibles_whatsapp.py`, sobre el fixture extendido de la 007 más el opt-in de A)
- `::test_interesado_sin_opt_in_no_es_elegible`: sin opt-in, `v_elegibles_whatsapp` está vacía, aunque A sea `interesado` y tenga teléfono publicado.
- `::test_con_opt_in_es_elegible`: con el opt-in aparece A, y nadie más.
- `::test_natural_con_opt_in_no_es_elegible`: A pasado por SQL a `tipo_titular='natural'` → no aparece.
- `::test_baja_por_cualquier_canal_excluye[enlace|respuesta|clasificador]`: después de `DarDeBaja` con esa `via`, A no aparece.
- `::test_baja_de_otro_lead_con_el_mismo_telefono_excluye`: otro lead con el mismo `telefono_hmac` y dado de baja → A no aparece (lo hace `v_leads_con_opt_out` de la 007; queda como regresión).
- `::test_mismo_telefono_dos_leads_un_solo_contacto`: dos leads con el mismo `telefono_hmac`, los dos con opt-in → `RedactarBorradoresWhatsapp` crea 1 contacto.
- `::test_ya_contactado_por_whatsapp_no_vuelve`: con un contacto `whatsapp` de A en cualquier estado, A no aparece.
- `::test_sin_whatsapp_comercial_no_es_elegible_asistido[sitio_web|osm_contacto|whatsapp_osm]`: A con opt-in y ese `telefono_canal` → no aparece en `v_elegibles_whatsapp_asistido`.
- `::test_whatsapp_comercial_sin_opt_in_no_es_elegible`: A con `whatsapp_comercial` publicado e `interesado`, sin opt-in → `v_elegibles_whatsapp_asistido` vacía.
- `::test_con_opt_in_y_whatsapp_comercial_es_elegible`: aparece A, y nadie más.
- `::test_contacto_meta_previo_excluye_asistido`: con un contacto de `whatsapp_meta` de A → A no aparece en la vista del asistido (`UNIQUE (tenant_id, lead_id, canal)`).

**Asistido** (`backend/tests/integration/test_whatsapp_asistido.py`, sobre el fixture de elegibles con A en `whatsapp_comercial` y opt-in, YAML real y `humano.usd_por_minuto = 0.25`)
- `::test_borrador_asistido_pendiente`: `adaptador='whatsapp_asistido'`, `estado='pendiente_aprobacion'`, cuerpo editable; un `POST /contactos/{id}/aprobar` con un cuerpo que quita "responda BAJA" → 422 `opt_out` y sigue `pendiente_aprobacion`.
- `::test_aprobar_con_cuerpo_fuera_de_pendiente_es_409[aprobado|descartado]`: 409 `estado_invalido` y el cuerpo guardado no cambia; el enlace sale siempre con el texto aprobado.
- `::test_sin_aprobacion_no_hay_enlace[pendiente_aprobacion|descartado]`: 409 `requiere_aprobacion`, sin `enlace_emitido_en` y 0 filas en `costos`.
- `::test_enlace_es_wa_me_al_numero_publicado`: aprobado → 200, `enlace` = `https://wa.me/<E.164 de A sin +>?text=<cuerpo url-encoded>`, `Cache-Control: no-store`, estado `enviando` y 0 filas en `costos` (todavía no envió nadie).
- `::test_reemitir_enlace_no_ocupa_cupo`: con `max_por_dia: 1`, dos llamadas sobre el mismo contacto → el mismo enlace y `enlace_emitido_en` sin cambios.
- `::test_tope_diario_cuenta_enlaces`: con `max_por_dia: 1` y 2 aprobados → el segundo da 409 `tope_diario` y sigue `aprobado`.
- `::test_freno_bloquea_enlace`: 1 contacto `whatsapp` entregado con baja `via='whatsapp'` → 409 `freno_whatsapp` y el aprobado sigue `aprobado`.
- `::test_sin_base_legal_no_hay_enlace`: `base_legal` nula por SQL → 409 `no_contactable` y `descartado`.
- `::test_marcar_enviado_escribe_minutos_humanos`: `enviado_en` y `entregado_en` puestos; 1 fila `minutos_humanos` con 1 minuto, 0.25, `proveedor='humano'`, el `lead_id` de A, `canal='whatsapp'`, `fuente` NULL y `gratis=false`.
- `::test_marcar_no_entregable_escribe_costo`: estado `no_entregable` y 1 fila `minutos_humanos`.
- `::test_marcar_descartado_sin_costo`: estado `descartado` y 0 filas en `costos`.
- `::test_marcar_dos_veces_es_409`: el segundo `marcar` → `estado_invalido` y sigue habiendo 1 fila de costo.
- `::test_marcar_sin_enlace_es_409[pendiente_aprobacion|aprobado|descartado]`: → `estado_invalido` y 0 filas en `costos`: no existe envío sin aprobación y enlace.
- `::test_respuesta_pegada_escribe_minutos_y_queda_sin_clasificar`: "Sí, cuénteme" → 1 respuesta `sin_clasificar`, `respuesta_texto_cifrado` sin el texto en claro, 1 fila `minutos_humanos` más y 0 llamadas al clasificador.
- `::test_respuesta_pegada_idempotente`: el mismo texto dos veces → 1 respuesta y 1 fila de costo.
- `::test_baja_pegada_da_de_baja_en_todos_los_canales[BAJA|NO|Stop]`: `pide_no_contacto` determinista, `opt_out_at` puesto, `solicitudes` suma `{via:'whatsapp', contacto_id}`, A sale de `v_contactables` de email (007) y `v_tasa_bloqueo['whatsapp'].bloqueos = 1`.
- `::test_respuesta_pegada_sobre_no_enviado[aprobado|enviando|no_entregable]`: 409 `estado_invalido`, 0 respuestas.
- `::test_contacto_de_otro_tenant_es_404[enlace-whatsapp|marcar|respuesta-pegada]`.
- `::test_enviar_aprobados_no_toca_asistido`: con un aprobado del asistido, `EnviarAprobados` no lo reclama y el transporte falso recibe 0 requests.

**Envío meta** (`backend/tests/integration/test_envio_whatsapp.py`, con `whatsapp_meta` habilitado en la config de prueba, `WhatsappMeta` sobre `httpx.MockTransport` y la tarifa de prueba `whatsapp.usd_por_plantilla_co = 0.30`; A sigue en `sitio_web`)
- `::test_borrador_es_plantilla_fija_pendiente`: `adaptador='whatsapp_meta'`, `redactor='plantilla_fija'`, `estado='pendiente_aprobacion'` y la `plantilla_version` de la config.
- `::test_whatsapp_comercial_va_al_asistido`: con los dos habilitados y un lead elegible con `whatsapp_comercial` → su borrador es del asistido, no de meta.
- `::test_editar_cuerpo_whatsapp_meta_es_422`: `plantilla_fija`.
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
- `backend/tests/contratos/test_canal_contacto.py` (007) suma `whatsapp_meta` con `httpx.MockTransport` y `whatsapp_asistido`:
  - meta: `enviar` devuelve un `message_id` y escribe su fila de costo; un error de transporte es `CanalNoDisponible`, sin el teléfono en el mensaje;
  - asistido: `enlace` es puro (0 requests de red, 0 filas en `costos`) y codifica bien un cuerpo con tildes, `&`, `?` y saltos de línea;
  - `::test_cada_canal_cumple_su_modo`: un canal `pull` implementa `leer_respuestas`, uno `push` implementa `verificar` y `parsear`, uno `manual` implementa solo `enlace`, y ninguno implementa métodos de otro modo.
- `test_api_auth.py::test_rutas_publicas_son_exactamente_estas`: la lista suma `/webhooks/whatsapp` (GET y POST), con el canal habilitado o no.
- `test_rls.py::test_tenant_b_no_accede_a[opt_in_whatsapp]` (la lista fija suma la tabla).
- `test_privilegios_supabase.py::test_anon_y_authenticated_sin_privilegios`: el assert previo exige `opt_in_whatsapp`, `v_contactables_whatsapp`, `v_elegibles_whatsapp` y `v_tasa_bloqueo`.
- `test_contacto_no_aparece_en_logs.py`: suma el teléfono de A en un envío por WhatsApp, el texto de un mensaje entrante por el webhook, y el enlace `wa.me` y el texto pegado del asistido.
- `test_costos_por_adaptador.py`: un `WhatsappMeta.enviar` que no pasa por `RegistroCostos` falla; un `marcar` o una `respuesta-pegada` del asistido que no escriben `minutos_humanos` fallan.
- `test_import_linter.py`: `httpx` hacia la Graph API solo en `contacto/infraestructura/`. El contrato de fuentes prohibidas no se toca, porque WhatsApp no es fuente.
- `test_migraciones.py`:
  - `::test_migracion_0009_sobre_0008_con_datos`: con contactos `email` existentes, `upgrade` conserva todo, y `downgrade` falla si hay algún contacto `whatsapp` (no se pierde una traza en silencio);
  - `::test_check_canal_admite_whatsapp_y_rechaza_sms`;
  - `::test_check_adaptador_coherente_con_canal`: `canal='email'` con `adaptador='whatsapp_asistido'` falla, y `enlace_emitido_en` en un contacto de meta falla;
  - `::test_check_via_y_registrado_por`: `via='humano'` sin `registrado_por` falla, y `via='palabra_clave'` con `registrado_por` falla.
- `test_baja.py` (007) suma `::test_baja_por_enlace_registra_contacto_id`: la entrada de `solicitudes` tiene el `contacto_id` del token.

**Tablero** (`backend/tests/integration/test_vistas_tablero.py`, se suma a la 007)

Corre sobre `fixture_whatsapp`. Parte del fixture extendido de la 007 (A `interesado` y C `rebote` por email, filas 7 y 8) y suma:
- el opt-in de A;
- un contacto `whatsapp` de A `enviado` y con `entregado_en`, con `whatsapp_plantilla` 0.30 y `gratis=false`;
- una respuesta `interesado` de A por WhatsApp.

`fixture_whatsapp_asistido` es el mismo, pero el contacto de A es del asistido: sin `whatsapp_plantilla`, con 1 fila `minutos_humanos` de 0.25 por el envío marcado y otra de 0.25 por la respuesta pegada.

Tests:
- `::test_costo_por_respuesta_whatsapp` (meta):
  - `lista = 0.85`: A 0.20 de `v_prorrateo` + 0.05 de la fila 7 (el email de A, que vino antes) + 0.30 de la fila 8 con `canal='whatsapp'` + 0.30 de la plantilla;
  - `real = 0.75`: 0.10 + 0.05 + 0.30 + 0.30;
  - divisor 1 lead → `0.85` / `0.75`.

  La fila 8 es de G, que no puede tener WhatsApp. Entra igual porque la vista suma todo `v_costos` con `canal='whatsapp'`, y eso es coherente con la definición de la 007.
- `::test_costo_por_respuesta_whatsapp_asistido` (sobre `fixture_whatsapp_asistido`):
  - `lista = 1.05`: 0.20 + 0.05 + 0.30 de la fila 8 + 0.25 del envío + 0.25 del registro;
  - `real = 0.95`: 0.10 + 0.05 + 0.30 + 0.25 + 0.25;
  - divisor 1 lead → `1.05` / `0.95`.
- `::test_email_de_lead_sin_whatsapp_no_entra_a_whatsapp`: `fixture_whatsapp_asistido` más una fila `email` de 0.05 para C y un contacto asistido de C en `descartado` (sin `enviado_en`). `whatsapp` sigue en `lista = 1.05` / `real = 0.95` con divisor 1: el email de C no entra, porque C no tiene contacto `whatsapp` con `enviado_en`. La fila 7 sí entra, porque A lo tiene.
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
- `frontend/src/mensajes/Mensajes.test.tsx::whatsapp_meta_se_aprueba_sin_editar`: un contacto de `whatsapp_meta` muestra el cuerpo sin edición y el botón Aprobar.
- `frontend/src/mensajes/Mensajes.test.tsx::asistido_abrir_en_whatsapp_solo_en_aprobado`: "Abrir en WhatsApp" aparece en `aprobado` y `enviando`, no en `pendiente_aprobacion`; abre el `enlace` de la respuesta en una pestaña nueva sin guardarlo; en `enviando` aparecen "Enviado", "No se pudo enviar" y "No lo envié".
- `frontend/src/mensajes/Mensajes.test.tsx::asistido_pegar_respuesta_solo_en_enviado`: el textarea "Pegar respuesta" aparece solo en `enviado` y manda el texto a `respuesta-pegada`.
- `frontend/src/tablero/Tablero.test.tsx::muestra_tasa_de_bloqueo_y_aviso_de_freno`: con `tasa ≥ 0.01` aparece el aviso "WhatsApp frenado: tasa de bloqueo 1 %".
- `frontend/src/tablero/Tablero.test.tsx::whatsapp_se_rotula_como_segundo_toque`: el costo por respuesta muestra las filas "email" y "email → whatsapp (opt-in)", y ninguna fila "whatsapp" sola.

**Evals**
- `uv run python -m evals.run` pasa con los 6 casos nuevos de `clasificacion_respuestas` y el baseline regenerado.

## Fuera del alcance
- **WhatsApp como primer toque, también con el asistido.** Meta exige opt-in, y la regla 2 también: un número publicado no es opt-in. Que lo envíe un humano no lo cambia.
- **Leer o automatizar el WhatsApp de la pyme** (WhatsApp Web, bots, extensiones). El asistido no ve el chat: el humano envía y pega. Automatizar una cuenta personal o Business sin API viola los términos de WhatsApp.
- **Envío automático desde el asistido.** Sin un humano que apriete enviar, no hay envío.
- **Un número distinto al publicado** ("escríbanme al 300…"). Puede ser el celular de una persona (regla 3). `# ponytail: el humano contesta por email; si un evento lo pide, se suma con la validación del dueño`.
- **Conversación libre dentro de la ventana de 24 h.** Solo se manda la plantilla; lo que sigue lo atiende la pyme desde su WhatsApp Business. `# ponytail: sin bandeja de chat; entra si la pyme la pide`.
- **Redacción con LLM para `whatsapp_meta`.** La plantilla la aprueba Meta y no puede variar. El asistido sí usa el `Redactor` de la 007.
- **Baja solo de WhatsApp.** Un BAJA por WhatsApp da de baja en todos los canales, que es lo más conservador. `# [VALIDAR]` si el dueño quiere baja por canal.
- **Reintento automático y reapertura del freno.** Ver los pasos 7.4 y 7.7 del flujo.
- **Varios números o varios tenants con WhatsApp.** Un número por despliegue (`WHATSAPP_TENANT_ID`). `# ponytail: tabla de ruteo phone_number_id → tenant cuando haya un segundo tenant`.
- **Medios, botones, plantillas con imagen.** Solo texto.
- **Opt-in fuera de una respuesta** (formulario web, QR). Lo ve la 010 si llega.
- **Rate limiting del webhook.** 012.

## Decisiones técnicas
**Módulo** `backend/app/modulos/contacto/` (el de la 007):
- `dominio/`:
  - `opt_in.py`: `admitidos(adaptadores_habilitados) -> set[str]` y `validar_opt_in(clasificacion, telefono_canal, admitidos, dado_de_baja)`;
  - `freno.py`: `frenado(bloqueos, entregados, maximo) -> bool`;
  - `plantilla.componer` suma la línea de WhatsApp y `plantilla.validar` suma el parámetro `canal`.
- `aplicacion/`:
  - `registrar_opt_in.py` (las dos vías);
  - `redactar_borradores_whatsapp.py` (con `adaptador`);
  - `emitir_enlace_whatsapp.py`, `marcar_contacto.py` y `registrar_respuesta_pegada.py` (asistido);
  - `procesar_webhook_whatsapp.py`;
  - `clasificar_respuestas_pendientes.py`;
  - `enviar_aprobados.py` suma el freno, el tope y el mapeo de errores por canal, y filtra `adaptador='whatsapp_meta'`.
- `infraestructura/`:
  - `whatsapp_asistido.py`: `enlace`, sin `httpx` ni secretos;
  - `whatsapp_meta.py`: adaptador con `httpx` (`enviar`, `verificar`, `parsear`).
- La API (`/respuestas/{id}/opt-in-whatsapp`, `/contactos/{id}/enlace-whatsapp`, `/contactos/{id}/marcar`, `/contactos/{id}/respuesta-pegada`, `/webhooks/whatsapp`) vive en `backend/app/api/` y no importa nada de Meta.

**Opt-in = pedido del lead + número publicado.** `respuesta_id NOT NULL` es la prueba de que el lead pidió WhatsApp: o escribió `WHATSAPP` (`via='palabra_clave'`, `registrado_por` NULL) o un humano leyó su respuesta y lo registró (`via='humano'`, `registrado_por` set). El número es el que la empresa publicó, nunca uno nuevo. Así se cumplen a la vez Meta (opt-in), el PRD y `solo_numeros_comerciales_publicados` (número comercial publicado), y la regla 3 (nada nominal). `cumplimiento.base_legal` sigue siendo la del lead (007) y se exige igual.

**El asistido nace `habilitado: true`.** La validación escrita del dueño (constitución:57) es para usar una cuenta o un proveedor de WhatsApp Business API, y el asistido no usa ninguno: el mensaje sale del WhatsApp de la pyme, enviado por una persona. Lo que sí le aplica de la regla 8 lo cumple igual: `max_por_dia` y freno < 1 %. El opt-in previo tampoco se relaja: es lo que exige la política de WhatsApp Business, con o sin API.

**Costo al marcar, no al emitir el enlace.** Emitir el enlace no cuesta nada: el humano todavía no hizo nada. El tiempo humano se escribe cuando el humano dice qué pasó (`enviado` o `no_entregable`) y cuando pega una respuesta. Un `descartado` no cuesta porque el humano se arrepintió antes de abrir WhatsApp. `# ponytail: minutos fijos por config; cronometrar el envío real si la diferencia importa`.

**Marcar `enviado` = entregado.** El asistido no recibe acuses. Si el humano lo mandó y WhatsApp no avisó que el número no existe, se toma como entregado, y así entra al denominador de la tasa de bloqueo. Si no salió, el humano marca `no_entregable`, que no es entrega.

**Un freno y un tope por adaptador, una tasa por canal.** Los dos adaptadores comparten `v_tasa_bloqueo['whatsapp']`: un BAJA por cualquiera de los dos frena los dos, que es lo conservador. El tope es de cada uno, porque mide cosas distintas: el asistido cuenta `enlace_emitido_en` de hoy (lo que el número de la pyme mandó) y meta cuenta filas `whatsapp_plantilla` (lo que la cuenta de Meta mandó).

**El enlace no se guarda.** Lleva el teléfono y el texto en claro. Se arma en cada pedido a partir de `telefono_cifrado` y el cuerpo, se devuelve con `no-store` y no toca logs. Re-emitirlo sobre `enviando` da el mismo texto porque sale de los mismos datos.

**Reparto por canal publicado.** Con los dos habilitados, `whatsapp_comercial` va al asistido y el resto a meta. Así un lead no recibe dos WhatsApp, y la vista lo garantiza por `UNIQUE (tenant_id, lead_id, canal)`.

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

**Variables de entorno nuevas** (Railway, servicio `api`, solo meta; el asistido no usa ninguna): `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_TENANT_ID`. La cuenta de Meta es nueva para el evento, o la existente solo con la validación escrita del dueño, registrada en `docs/decisiones.md` y referenciada en `validacion_dueno` (constitución, reglas del proyecto).

**Migración `0009_whatsapp.py`** (a mano, revisada por un humano):

| Tabla / vista | Definición |
|---|---|
| `contactos` | `CHECK (canal IN ('email', 'whatsapp'))` reemplaza a `canal = 'email'`. `UNIQUE (tenant_id, lead_id, canal)` sigue. `+ entregado_en timestamptz NULL` (solo lo llena WhatsApp). `+ adaptador text NOT NULL CHECK (adaptador IN ('smtp_email', 'whatsapp_meta', 'whatsapp_asistido'))`, con backfill `smtp_email` en las filas existentes, y `CHECK ((canal = 'email') = (adaptador = 'smtp_email'))`. `+ enlace_emitido_en timestamptz NULL` con `CHECK (enlace_emitido_en IS NULL OR adaptador = 'whatsapp_asistido')`. |
| `opt_in_whatsapp` | `id`, `tenant_id`, `lead_id` FK, `respuesta_id` FK `respuestas` NOT NULL, `via text NOT NULL CHECK (via IN ('palabra_clave', 'humano'))`, `registrado_por` FK `usuarios` NULL, `registrado_en`. `CHECK ((via = 'humano') = (registrado_por IS NOT NULL))`. `UNIQUE (tenant_id, lead_id)`. RLS por `tenant_id`. Sin columnas de contacto. |
| `respuestas` | Sin cambios de esquema: `message_id` guarda el `wamid` o `pegada:<hmac>`. Si la 007 fijó `solicitudes.via` con CHECK, se amplía con `whatsapp`. |
| `v_contactables_whatsapp` | opt-in ⋈ lead con: `juridica`; `telefono_cifrado` no nulo y `telefono_canal IN ('sitio_web', 'osm_contacto', 'whatsapp_comercial')`; `encaje ≠ no_encaja`; `fusionado_en IS NULL`; sin `revision_dedup` pendiente; con `cumplimiento` y `base_legal`; fuera de `v_leads_con_opt_out`. Qué subconjunto usa cada adaptador lo decide la aplicación con `admitidos`. |
| `v_elegibles_whatsapp` | `v_contactables_whatsapp` sin contacto `whatsapp` previo del lead ni de otro lead con el mismo `telefono_hmac`. `DISTINCT ON (telefono_hmac)` por `registrado_en`. |
| `v_elegibles_whatsapp_asistido` | `v_elegibles_whatsapp` con `telefono_canal = 'whatsapp_comercial'`. |
| `v_tasa_bloqueo` | Por `canal`: `entregados` = contactos con `entregado_en IS NOT NULL` (en `email`, `enviado − rebotado`, el mismo criterio de `v_tablero_fuentes` de la 007; en el asistido lo pone el marcado `enviado`); `bloqueos` = contactos en `enviando`, `enviado` o `rebotado` cuyo `id` aparece como `contacto_id` en una entrada `tipo='baja'` de `solicitudes`; `tasa = bloqueos / NULLIF(entregados, 0)`. |

Todas las vistas con `security_invoker = true`. No redondean.

**Precisión de `v_costo_por_respuesta` (007):**
- el divisor cuenta leads distintos con una respuesta real cuyo `contactos.canal` es ese canal;
- el costo de descubrimiento de un lead entra en cada canal que lo contactó, así que `costo_por_respuesta` no se suma entre canales;
- para `whatsapp`, el numerador suma además el costo `email` de los leads con contacto `whatsapp` y `enviado_en IS NOT NULL` (el mismo criterio del prorrateo de la 007). Es el costo del primer toque que trajo el opt-in, y por eso la fila se rotula "email → whatsapp (opt-in)". El de `email` no cambia.

## Plan de tareas (TDD, en orden)
**Corte 1: base compartida y asistido, con front (≈ 2 h 15)**
1. Rojo: `test_config_whatsapp.py` → verde con la carga de los dos adaptadores, el gate de meta y `ConfigInvalida`.
2. Rojo: `test_migraciones.py` (0009) + `test_rls[opt_in_whatsapp]` + `test_privilegios_supabase` → verde con `0009_whatsapp.py`.
3. Rojo: `test_plantilla.py` (WhatsApp y la línea del email) + `test_freno.py` → verde con `componer`, `validar(canal=...)` y `frenado`.
4. Rojo: `test_opt_in_whatsapp.py` + `test_opt_in_palabra_clave.py` → verde con `admitidos`, `validar_opt_in`, `RegistrarOptIn`, el endpoint y `WHATSAPP` en la clasificación determinista.
5. Rojo: `test_elegibles_whatsapp.py` → verde con las vistas y `RedactarBorradoresWhatsapp(adaptador='whatsapp_asistido')`.
6. Rojo: `test_baja_por_enlace_registra_contacto_id` + `::test_tasa_bloqueo_por_canal` → verde con `contacto_id` en `DarDeBaja` y `v_tasa_bloqueo`.
7. Rojo: `test_canal_contacto.py[whatsapp_asistido]` + `test_whatsapp_asistido.py` + `test_costos_por_adaptador` (asistido) + `test_contacto_no_aparece_en_logs` (enlace y texto pegado) → verde con `WhatsappAsistido.enlace`, `EmitirEnlaceWhatsapp`, `MarcarContacto` y `RegistrarRespuestaPegada`.
8. Rojo: `::test_costo_por_respuesta_whatsapp_asistido` + `::test_email_de_lead_sin_whatsapp_no_entra_a_whatsapp` → verde con la precisión de `v_costo_por_respuesta`.
9. Rojo: `Respuestas.test.tsx`, los dos tests del asistido en `Mensajes.test.tsx` y los dos de `Tablero.test.tsx` → verde.

Cierre del corte 1, prueba manual con un lead de prueba cuyo `whatsapp_comercial` es un número del equipo:
1. el email sale con la línea de WhatsApp y se responde `WHATSAPP`;
2. el opt-in queda con `via='palabra_clave'`;
3. se aprueba el borrador, se abre el enlace, se envía desde un teléfono y se marca `enviado`;
4. se pega la respuesta `BAJA`;
5. se comprueba que el lead quedó dado de baja también en email, que el tablero muestra el freno y la fila "email → whatsapp (opt-in)", y que se miden los minutos reales para `minutos_por_envio` y `minutos_por_registro`.

**Corte 2: meta (≈ 2 h)**
10. Rojo: `test_canal_contacto.py[whatsapp_meta]` + `test_envio_whatsapp.py` + `test_costos_por_adaptador` (meta) → verde con `WhatsappMeta.enviar`, el freno, el tope y el mapeo de errores.
11. Rojo: `test_webhook_whatsapp.py` + `test_rutas_publicas_son_exactamente_estas` + `test_contacto_no_aparece_en_logs` (webhook) → verde con `verificar`, `parsear` y `ProcesarWebhookWhatsapp`.
12. Rojo: `::test_costo_por_respuesta_whatsapp` → verde.

Cierre del corte 2, solo con la validación del dueño: la misma prueba manual con la cuenta del evento y un número de prueba de Meta (`# [VALIDAR]` sandbox), registrando el opt-in a mano y respondiendo BAJA por WhatsApp.

**Corte 3: clasificación y eval (≈ 30–45 min)**
13. Rojo: `test_clasificar_pendientes_whatsapp.py` → verde con `ClasificarRespuestasPendientes`.
14. Rojo: los 6 casos nuevos de `clasificacion_respuestas` → baseline regenerado, con la justificación en el PR.

**Corte 4: front de meta y doc (≈ 15 min)**
15. Rojo: `Mensajes.test.tsx::whatsapp_meta_se_aprueba_sin_editar` → verde.
16. Doc:
    - `docs/arquitectura-backend.md`: el puerto `CanalContacto` con `modo`, el asistido, el webhook y el freno;
    - `docs/arquitectura-frontend.md`;
    - README: el asistido "nace prendido" y por qué; las variables `WHATSAPP_*` y "meta nace apagado".

**Orden de corte**, si no alcanza el tiempo (qué se corta y a dónde va):
1. **Corte 4:** sin meta prendido no hace falta su pantalla. La doc pasa a la 013.
2. **Corte 2:** `whatsapp_meta` queda en `habilitado: false` y la demo muestra su gate (`canal_no_disponible`, webhook 404). La rama de meta pasa a la 012.
3. **Corte 3:** las respuestas pegadas que no son BAJA/NO/STOP quedan `sin_clasificar` y un humano las resuelve con la baja manual de la 007 (`POST /respuestas/{id}/baja`). Los casos del eval pasan a la 012.
4. **El corte 1 no se corta.**
   - Si el corte 1 no arranca antes de las **12:45 del domingo**, no se empieza. Con ≈ 2 h 15 no llega verde a las 3pm (PRD §9).
   - Si a las 3pm el corte 1 no está verde, se corta el slice entero: la rama no se mergea, los dos adaptadores quedan en `habilitado: false` y el MVP es solo email.

## Riesgos
- **La validación del dueño o la tarifa no llegan:** meta no se prende. El asistido no depende de ninguna de las dos. Mitigación: meta se prueba entero con `MockTransport`, y la demo muestra su gate como cumplimiento funcionando.
- **El humano marca mal** (marca `enviado` sin enviar, o pega la respuesta en otro contacto): el tablero miente y el costo también. Mitigación: los botones aparecen solo en el estado que corresponde, el marcado no se puede repetir y la respuesta pegada va al contacto de la pantalla, no a un lead elegido a mano. `# ponytail: sin deshacer el marcado; un humano lo corrige por SQL si pasa en la demo`.
- **WhatsApp bloquea el número de la pyme** por mandar muchos mensajes a no contactos: es el riesgo propio del asistido, porque el número es el de la pyme y no uno del evento. Mitigación: solo se escribe a quien pidió WhatsApp, `max_por_dia` bajo y el freno < 1 %. `# [VALIDAR]` el tope con la pyme antes de la demo.
- **Pocos leads con `whatsapp_comercial`:** depende de cuántos sitios publican un enlace `wa.me` (006). Con n = 0 la línea no sale en ningún email y el asistido no tiene a quién escribir. Es el resultado honesto, y el tablero lo muestra como "sin dato".
- **Meta tarda en aprobar la plantilla** (horas o días): sin plantilla aprobada no hay envío real. Mitigación: pedirla el sábado y, si no llega, usar el número de prueba de Meta en la demo. `# [VALIDAR]`.
- **Pocos leads con opt-in:** aun con `whatsapp_comercial`, el canal puede quedar con n = 0 o 1 en la demo, porque solo cuenta quien pidió WhatsApp.
- **El webhook no tiene el formato de los fixtures:** los payloads de `tests/fixtures/whatsapp/` salen de la doc de Meta (`# [VALIDAR]`) y se reemplazan por uno real en la prueba manual.
- **Códigos de baja equivocados:** un `failed` por otra causa daría de baja de más. Es el lado seguro del error, y se ajusta `codigos_baja` en la config.
- **Filas trabadas en `enviando` después de un timeout:** las resuelve un humano, igual que en la 007. Con el tope bajo son pocas.
- **El webhook público es superficie de ataque:** firma HMAC obligatoria, tope de tamaño sin leer el resto, `phone_number_id` verificado, idempotencia, cero respuestas automáticas y texto entrante tratado como hostil antes del LLM. El agente `security` lo revisa en el PR.
- **Cuándo cortar:** ver el orden de corte. Nunca se cortan el gate de meta apagado por defecto, el opt-in previo también en el asistido, el opt-in ligado a una respuesta y al número publicado, la baja por WhatsApp en todos los canales, el freno y la firma del webhook.
