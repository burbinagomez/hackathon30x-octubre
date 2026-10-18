# Tasks: 007 — Email por SMTP, respuestas mínimas y baja

**Input**: `specs/007-email-respuestas/plan.md` (corte de demo) y `spec.md`.

**Formato**: `- [ ] TNNN [P?] [Paso n] descripción con ruta`

- **Rojo**: el test falla por un `assert` sobre el resultado, nunca por `ImportError` ni `AttributeError`. Los esqueletos van antes.
- **Mutación**: un cambio de una línea, con nombre, que pone el test en rojo. Se corre, se ve rojo y se revierte.
- **(security)**: lo revisa security antes de aceptarlo. **(advisor)**: lo revisa el advisor.
- Sin envíos reales: todo test de envío usa `tests/smtp_falso.py` en `127.0.0.1` y puerto efímero.

## Fase 1: Puerta y setup (Paso 0)

- [x] T001 [Paso 0] Daniel aprobó el DDL con condiciones: número = siguiente libre en `main` al mergear; grants/revokes también en las vistas; P1 con `--dry-run` previo, tope 20, elegibilidad y `EMAIL_MODO=prueba`.
- [x] T002 [P] [Paso 0] Esqueletos de `app/modulos/contacto/{dominio,aplicacion,infraestructura}` con firmas y `raise NotImplementedError`; `app.modulos.contacto` en `containers` de import-linter y contrato `contacto.dominio` ↛ `smtplib`, `cryptography`.
- [x] T003 [P] [Paso 0] `Settings`: `smtp_host`, `smtp_port`, `smtp_usuario`, `smtp_clave: SecretStr`, `smtp_seguridad` (`ssl|starttls|ninguna`), `remitente`, `baja_secret: SecretStr`, `api_base_url`, `email_modo` (`prueba` por defecto | `real`), `email_prueba_destinos: list[str]`. `::test_email_modo_por_defecto_es_prueba`. Mutación `sabotaje_modo_real_por_defecto`. (security)
- [x] T004 [P] [Paso 0] `tests/smtp_falso.py`: `socketserver` con EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT; guarda los mensajes y puede rechazar un RCPT con 550 o cortar en DATA.

## Fase 2: Dominio (Paso 1)

- [x] T010 [Paso 1] `tests/unit/contacto/test_tokens.py`: `::test_ida_y_vuelta`, `::test_un_bit_cambiado_falla`, `::test_proposito_distinto_falla`, `::test_otro_tenant_falla`, `::test_compara_con_compare_digest` (spy). Mutación `sabotaje_token_sin_proposito`: firmar sin el propósito.
- [x] T011 [Paso 1] `tests/unit/contacto/test_plantilla.py`: `::test_mensaje_lleva_enlace_de_baja` (URL exacta con el token de ese contacto), `::test_pie_completo` (identificación, origen según `canal_origen`, `/privacidad`), `::test_url_de_baja_de_otro_contacto_no_valida`, `::test_menos_de_100_palabras`. Mutación `sabotaje_mensaje_sin_baja`: `componer` sin la línea de baja. (security)
- [x] T012 [Paso 1] Implementar `tokens.py` y `plantilla.py` hasta verde.

## Fase 3: Adaptador `smtp_email` (Paso 2) — security

- [x] T020 [Paso 2] `tests/contratos/test_smtp_email.py` contra el SMTP falso: `::test_headers_list_unsubscribe_y_message_id` (mailto + https a `API_BASE_URL`, `List-Unsubscribe-Post: List-Unsubscribe=One-Click`, `text/plain`, sin adjuntos), `::test_autentica_con_usuario_y_clave`, `::test_error_de_transporte_es_canal_no_disponible_sin_direccion`.
- [x] T021 [Paso 2] `::test_costo_se_registra_aunque_smtp_falle`: RCPT 550 → 1 fila `email_envio`, `unidades=1`, `canal='email'`, `lead_id`, `lote_id`, `gratis=true`, `costo_unitario` `type(v) is Decimal`. Mutación `sabotaje_costo_despues_del_smtp`: registrar después de `send_message`.
- [x] T022 [Paso 2] `::test_contacto_no_aparece_en_logs`: con `caplog` en DEBUG y `SMTPRecipientsRefused`, ni la dirección ni `smtp_clave` aparecen en logs, en `str(excepcion)` ni en `repr(LeadContactable)`. Mutación `sabotaje_log_con_destinatario`. (security)
- [x] T023 [Paso 2] `::test_ninguna_solo_con_localhost`: `smtp_seguridad='ninguna'` con otro host → error de config. Mutación `sabotaje_sin_tls_remoto`. (security)
- [x] T024 [Paso 2] `test_costos_por_adaptador.py` suma los `CanalContacto` (`RegistroCostos` en el `__init__`).
- [x] T025 [Paso 2] Implementar `smtp_email.py` hasta verde.

## Fase 4: Migración (Paso 3) — después de T001

- [x] T030 [Paso 3] `supabase/migrations/<siguiente libre>_contactos.sql` con el DDL aprobado; `app/modelos.py` suma `contactos`. El número se recalcula contra `main` antes del merge.
- [x] T031 [Paso 3] `test_rls[contactos]` y `test_privilegios_supabase` en verde sin tocarlos; `test_migraciones` (drift vacío). `::test_un_solo_email_por_lead`: `INSERT` duplicado → `23505`. `::test_privilegios_vistas`: `app_rt` tiene `SELECT` en las dos vistas y `anon`/`authenticated` no tienen nada. Mutación `sabotaje_vista_sin_revoke`: sacar el revoke de una vista. (security) Nota: la 0002 ya cierra los default privileges, así que el sabotaje solo muere con `::test_la_migracion_cierra_sus_objetos_aunque_supabase_reabra_los_default_privileges`, que los reabre en una transacción. `test_rls` sí se tocó: suma `contactos`, las dos vistas y `SIN_DELETE`.

## Fase 5: Envío (Paso 4) — advisor

- [x] T040 [Paso 4] `tests/integration/test_envio_email.py` con `LeadsContactablesFalso` y SMTP falso: `::test_aprobado_que_sigue_elegible_se_envia` (camino feliz, usa `busquedas.mensaje_base`), `::test_envio_setea_base_legal`.
- [x] T041 [Paso 4] `::test_sin_base_legal_no_envia`: `base_legal` forzada a nula entre reclamo y envío → `vigente()` falso (sin excepción), 0 mensajes, `descartado`, la corrida sigue. Mutación `sabotaje_sin_base_legal`: saltar el chequeo. (security)
- [x] T042 [Paso 4] `::test_persona_natural_no_se_envia` y `::test_sin_canal_publicado_no_se_envia`. Mutación `sabotaje_natural`: sacar el filtro `tipo_titular`. (security)
- [x] T043 [Paso 4] `::test_dos_envios_en_paralelo_mandan_uno` (dos hilos, conexiones distintas) y `::test_limite_diario_deja_el_exceso_aprobado` (esta mitad, recortada: ver Recortes 3). Mutación `sabotaje_sin_reclamo`: ignorar el resultado del reclamo.
- [x] T044 [Paso 4] `::test_costo_en_libro_por_envio`: N envíos → N filas `email_envio` con `lote_id = busqueda_id`, también en los que fallaron.
- [x] T046 [Paso 4] `::test_enviar_sin_dry_run_falla`: sin `--dry-run` previo → `SinVistaPrevia`, 0 mensajes, 0 costos. `::test_lead_nuevo_despues_del_dry_run_no_sale`. Mutación `sabotaje_enviar_crea_contactos`: que `enviar` cree el contacto si no existe. (security)
- [x] T04A [Paso 4] `::test_mensaje_base_cambiado_frena`: `--dry-run`, se edita `busquedas.mensaje_base`, `enviar` → `MensajeCambio`, 0 mensajes, 0 costos; otro `--dry-run --rehacer` lo destraba (el `--dry-run` solo también frena con `MensajeCambio`). `enviar` recompone con el `mensaje_base` vigente y compara contra `contactos.cuerpo` (sin DDL nuevo). Mutación `sabotaje_sin_chequeo_de_cambio`. (security)
- [x] T04B [Paso 4] `::test_dry_run_imprime_resumen_sin_direcciones`: la salida trae cuántos se enviarían, el modo (`prueba`/`real`) y un ejemplo del mensaje con el enlace de baja; ninguna dirección de los leads aparece (ni la de prueba). Mutación `sabotaje_dry_run_con_direccion`. (security)
- [x] T047 [Paso 4] `::test_tope_20_por_corrida`: 25 elegibles con dry-run → 20 mensajes, 5 quedan `aprobado`. Mutación `sabotaje_sin_tope`.
- [x] T048 [Paso 4] `::test_modo_prueba_solo_destinos_de_prueba`: modo `prueba`, un lead en la lista y otro no → 1 mensaje, el otro `aprobado`, 1 costo. `::test_modo_prueba_lista_vacia_no_manda`. Mutación `sabotaje_prueba_sin_filtro`: ignorar la lista en modo `prueba`. (security)
- [x] T049 [Paso 4] `::test_sin_fila_de_cumplimiento_no_envia` y `::test_con_opt_out_no_envia`. Mutación `sabotaje_sin_chequeo_opt_out`. (security)
- [x] T045 [Paso 4] Implementar `EnviarABusqueda`, `repositorio_contactos.py` y `app.cli enviar [--dry-run] [--rehacer]` hasta verde; con `EMAIL_MODO=real` y sin `/baja/{token}` en la api, el CLI sale con 2 (`sabotaje_real_sin_baja`) (también T046–T049, T04A, T04B). `--dry-run` no imprime direcciones.

## Fase 6: Baja (Paso 5) — security

- [ ] T050 [Paso 5] `tests/integration/test_api_baja.py`: `::test_get_muestra_confirmacion_y_no_da_de_baja`, `::test_post_da_de_baja_y_es_idempotente` (`via='enlace'`), `::test_one_click_rfc8058_sin_sesion`, `::test_token_invalido_404_generico` (alterado, `msgid` como baja, basura: mismo cuerpo), `::test_baja_no_expone_el_email`.
- [ ] T051 [Paso 5] `::test_opt_out_es_monotonico`: dos bajas → `opt_out_at` de la primera, 2 entradas en `solicitudes`. Mutación `sabotaje_baja_no_monotonica`: `opt_out_at = now()` sin `COALESCE`.
- [ ] T052 [Paso 5] `::test_baja_cierra_todos_los_canales`: tras la baja, el lead no sale en `de_busqueda(..., 'email')` ni en `de_busqueda(..., 'whatsapp')`, y todos sus `contactos` quedan con `bloqueo=true`. Mutación `sabotaje_baja_un_solo_canal`: filtrar el bloqueo por `canal`.
- [ ] T053 [Paso 5] `::test_baja_entre_reclamo_y_envio_gana`: baja después de crear el contacto → 0 mensajes, `descartado`.
- [ ] T054 [Paso 5] `test_auth.py`: `test_sin_token_da_401` excluye `RUTAS_PUBLICAS`; `::test_rutas_publicas_son_exactamente_estas`.
- [ ] T055 [Paso 5] Implementar `DarDeBaja`, `api/baja.py`, `app.cli baja --contacto <id>` (`via='humano'`) hasta verde.

## Fase 7: Respuestas y tasa (Paso 6)

- [ ] T060 [Paso 6] `tests/integration/test_respuestas_manual.py`: `::test_marcar_respondio_es_idempotente`, `::test_no_se_marca_un_no_enviado` (CHECK), `::test_tasa_por_canal` (2 enviados, 1 respondió → `0.5`), `::test_tasa_sin_envios_es_sin_dato`. Mutación `sabotaje_tasa_sobre_todos`: dividir por `count(*)` en vez de enviados.
- [ ] T061 [Paso 6] Implementar `MarcarRespondio`, `TasaRespuesta`, `app.cli respondio` y `app.cli tasa-respuesta` hasta verde.

## Fase 8: Revisión, corrida real y docs (Paso 7)

- [ ] T070 [Paso 7] security revisa cumplimiento y secretos sobre el diff (parada).
- [ ] T071 [Paso 7] Un envío real a una casilla nuestra, avisado antes; baja por el enlace desde esa casilla.
- [ ] T072 [P] [Paso 7] `docs/arquitectura-backend.md`: módulo `contacto`, puertos y `RUTAS_PUBLICAS`.

## Dependencias

- T001 bloquea la Fase 4; la 4 bloquea la 5, 6 y 7.
- Fases 2 y 3 corren sin la migración y en paralelo.
- `LeadsContactablesPostgres` espera el merge de la 0008 (006); hasta entonces, el falso.

## Orden de corte

1. Fase 7 queda en `respondio` + `tasa-respuesta` por CLI (ya es el mínimo).
2. `GET /baja/{token}` con página de confirmación → solo `POST` y baja manual por CLI.
3. Límite diario (T043, segunda mitad). El tope de 20 por corrida (T047) no se corta.
Nunca se cortan: base legal, costo por envío, enlace de baja, baja que cierra todos los canales, logs sin contacto, `--dry-run` previo, tope por corrida, `EMAIL_MODO=prueba` por defecto.
