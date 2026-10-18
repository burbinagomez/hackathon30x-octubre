# Tasks: 007 — Email por SMTP, respuestas mínimas y baja

**Input**: `specs/007-email-respuestas/plan.md` (corte de demo) y `spec.md`.

**Formato**: `- [ ] TNNN [P?] [Paso n] descripción con ruta`

- **Rojo**: el test falla por un `assert` sobre el resultado, nunca por `ImportError` ni `AttributeError`. Los esqueletos van antes.
- **Mutación**: un cambio de una línea, con nombre, que pone el test en rojo. Se corre, se ve rojo y se revierte.
- **(security)**: lo revisa security antes de aceptarlo. **(advisor)**: lo revisa el advisor.
- Sin envíos reales: todo test de envío usa `tests/smtp_falso.py` en `127.0.0.1` y puerto efímero.

## Fase 1: Puerta y setup (Paso 0)

- [ ] T001 [Paso 0] Daniel aprueba el DDL de la 0010 (plan, "Migración"). Hasta entonces, solo Fases 2 y 3.
- [ ] T002 [P] [Paso 0] Esqueletos de `app/modulos/contacto/{dominio,aplicacion,infraestructura}` con firmas y `raise NotImplementedError`; `app.modulos.contacto` en `containers` de import-linter y contrato `contacto.dominio` ↛ `smtplib`, `cryptography`.
- [ ] T003 [P] [Paso 0] `Settings`: `smtp_host`, `smtp_port`, `smtp_usuario`, `smtp_clave: SecretStr`, `smtp_seguridad` (`ssl|starttls|ninguna`), `remitente`, `baja_secret: SecretStr`, `api_base_url`.
- [ ] T004 [P] [Paso 0] `tests/smtp_falso.py`: `socketserver` con EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT; guarda los mensajes y puede rechazar un RCPT con 550 o cortar en DATA.

## Fase 2: Dominio (Paso 1)

- [ ] T010 [Paso 1] `tests/unit/contacto/test_tokens.py`: `::test_ida_y_vuelta`, `::test_un_bit_cambiado_falla`, `::test_proposito_distinto_falla`, `::test_otro_tenant_falla`, `::test_compara_con_compare_digest` (spy). Mutación `sabotaje_token_sin_proposito`: firmar sin el propósito.
- [ ] T011 [Paso 1] `tests/unit/contacto/test_plantilla.py`: `::test_mensaje_lleva_enlace_de_baja` (URL exacta con el token de ese contacto), `::test_pie_completo` (identificación, origen según `canal_origen`, `/privacidad`), `::test_url_de_baja_de_otro_contacto_no_valida`, `::test_menos_de_100_palabras`. Mutación `sabotaje_mensaje_sin_baja`: `componer` sin la línea de baja. (security)
- [ ] T012 [Paso 1] Implementar `tokens.py` y `plantilla.py` hasta verde.

## Fase 3: Adaptador `smtp_email` (Paso 2) — security

- [ ] T020 [Paso 2] `tests/contratos/test_smtp_email.py` contra el SMTP falso: `::test_headers_list_unsubscribe_y_message_id` (mailto + https a `API_BASE_URL`, `List-Unsubscribe-Post: List-Unsubscribe=One-Click`, `text/plain`, sin adjuntos), `::test_autentica_con_usuario_y_clave`, `::test_error_de_transporte_es_canal_no_disponible_sin_direccion`.
- [ ] T021 [Paso 2] `::test_costo_se_registra_aunque_smtp_falle`: RCPT 550 → 1 fila `email_envio`, `unidades=1`, `canal='email'`, `lead_id`, `lote_id`, `gratis=true`, `costo_unitario` `type(v) is Decimal`. Mutación `sabotaje_costo_despues_del_smtp`: registrar después de `send_message`.
- [ ] T022 [Paso 2] `::test_contacto_no_aparece_en_logs`: con `caplog` en DEBUG y `SMTPRecipientsRefused`, ni la dirección ni `smtp_clave` aparecen en logs, en `str(excepcion)` ni en `repr(LeadContactable)`. Mutación `sabotaje_log_con_destinatario`. (security)
- [ ] T023 [Paso 2] `::test_ninguna_solo_con_localhost`: `smtp_seguridad='ninguna'` con otro host → error de config. Mutación `sabotaje_sin_tls_remoto`. (security)
- [ ] T024 [Paso 2] `test_costos_por_adaptador.py` suma los `CanalContacto` (`RegistroCostos` en el `__init__`).
- [ ] T025 [Paso 2] Implementar `smtp_email.py` hasta verde.

## Fase 4: Migración (Paso 3) — después de T001

- [ ] T030 [Paso 3] `supabase/migrations/0010_contactos.sql` con el DDL aprobado; `app/modelos.py` suma `contactos`.
- [ ] T031 [Paso 3] `test_rls[contactos]` y `test_privilegios_supabase` en verde sin tocarlos; `test_migraciones` (drift vacío). `::test_un_solo_email_por_lead`: `INSERT` duplicado → `23505`.

## Fase 5: Envío (Paso 4) — advisor

- [ ] T040 [Paso 4] `tests/integration/test_envio_email.py` con `LeadsContactablesFalso` y SMTP falso: `::test_aprobado_que_sigue_elegible_se_envia` (camino feliz, usa `busquedas.mensaje_base`), `::test_envio_setea_base_legal`.
- [ ] T041 [Paso 4] `::test_sin_base_legal_no_envia`: `base_legal` forzada a nula entre reclamo y envío → `SinBaseLegal`, 0 mensajes, `descartado`, la corrida sigue. Mutación `sabotaje_sin_base_legal`: saltar el chequeo. (security)
- [ ] T042 [Paso 4] `::test_persona_natural_no_se_envia` y `::test_sin_canal_publicado_no_se_envia`. Mutación `sabotaje_natural`: sacar el filtro `tipo_titular`. (security)
- [ ] T043 [Paso 4] `::test_dos_envios_en_paralelo_mandan_uno` (dos hilos, conexiones distintas) y `::test_limite_diario_deja_el_exceso_aprobado`. Mutación `sabotaje_sin_reclamo`: `UPDATE` sin `WHERE estado='aprobado'`.
- [ ] T044 [Paso 4] `::test_costo_en_libro_por_envio`: N envíos → N filas `email_envio` con `lote_id = busqueda_id`, también en los que fallaron.
- [ ] T045 [Paso 4] Implementar `EnviarABusqueda`, `repositorio_contactos.py` y `app.cli enviar [--dry-run]` hasta verde. `--dry-run` no imprime direcciones.

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
- Fases 2 y 3 corren sin la 0010 y en paralelo.
- `LeadsContactablesPostgres` espera el merge de la 0008 (006); hasta entonces, el falso.

## Orden de corte

1. Fase 7 queda en `respondio` + `tasa-respuesta` por CLI (ya es el mínimo).
2. `GET /baja/{token}` con página de confirmación → solo `POST` y baja manual por CLI.
3. Límite diario (T043, segunda mitad).
Nunca se cortan: base legal, costo por envío, enlace de baja, baja que cierra todos los canales, logs sin contacto.
