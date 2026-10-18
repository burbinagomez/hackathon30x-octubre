# Auditoría de seguridad: 007 email, respuestas y baja (T070)

Fecha: 2026-10-18. Alcance: `git diff origin/main...HEAD` de `feature/007-email` (43 archivos). Solo lectura;
no se tocó código. Marco: OWASP Top 10 edición 2025 (consultada hoy en top10.owasp.org) y `pip-audit`
sobre el entorno instalado. Primer informe de esta carpeta: el formato es tabla resumen, un bloque por
hallazgo, "Medido" y "No verificado".

## Resumen

| # | Hallazgo | Archivo:línea | Severidad | Eje |
|---|----------|---------------|-----------|-----|
| 1 | La guarda de `EMAIL_MODO=real` mira la ruta en el propio proceso, no en la API desplegada: con `BAJA_SECRET` ausente o distinta en la API, salen mails reales con enlaces de baja muertos | `backend/app/cli.py:122-125`, `:138-140`; `backend/app/config.py:68` | medio | cumplimiento |
| 2 | Cada POST a `/baja/{token}` anexa una entrada a `cumplimiento.solicitudes` sin tope ni rate limit | `backend/app/modulos/contacto/infraestructura/repositorio_contactos.py:73-75` | bajo | A10 |
| 3 | `reclamar` sobrescribe `base_legal` sin condición | `repositorio_contactos.py:49` | bajo | cumplimiento |
| 4 | `smtp_usuario` es `str`, no `SecretStr`: sale en `repr(SettingsEmail)` y el test de repr no lo cubre | `backend/app/config.py:83`; `backend/tests/unit/test_config_email.py:55-59` | bajo | A04 |
| 5 | Cupo diario recortado por decisión documentada: `enviar` repetido no tiene techo por día | `backend/app/modulos/contacto/aplicacion/envio.py:13`; `specs/007-email-respuestas/tasks.md:90` | info | cumplimiento |
| 6 | El REVOKE a `anon`/`authenticated` solo corre si existen los dos roles | `supabase/migrations/0009_contactos.sql:46-48` | info | A02 |
| 7 | GET con token firmado de un contacto inexistente responde 200; POST responde 404 | `backend/app/api/baja.py:26-31` vs `:34-38` | info | A01 |
| 8 | El flujo real de `enviar` es inalcanzable hoy: el armado Postgres lanza `NotImplementedError` | `backend/app/cli.py:128-130` | info | alcance |

0 críticos, 0 altos, 1 medio, 3 bajos, 4 info.

## Estado después de los arreglos

| # | Estado | Commit |
|---|--------|--------|
| 1 | Arreglado: la guarda de modo real hace GET a `API_BASE_URL/baja/<token>` con un token firmado por la `BAJA_SECRET` local y exige 200 | 401e05a |
| 2 | Arreglado: solo la primera baja anexa a `solicitudes` | d5d1043 |
| 3 | Arreglado: `COALESCE(base_legal, :bl)` | d5d1043 |
| 4 | Arreglado: `smtp_usuario` es `SecretStr` y el test de repr lo cubre | d5d1043 |
| 5 | Abierto, documentado en el PR | — |
| 6 | Abierto, documentado en el PR | — |
| 7 | Se mantiene a propósito: el GET no muta ni expone datos, y la guarda del #1 depende de ese 200 | — |
| 8 | Arreglado: `LeadsContactablesPostgres` y `_armar_envio_postgres`, con e2e de la CLI en modo prueba | 2b9a0ce |

## Hallazgos

### 1. La guarda de modo real no verifica la API desplegada (medio)

```python
# backend/app/cli.py:122-125
def _hay_ruta_de_baja() -> bool:
    from app.main import app
    return "/baja/{token}" in app.openapi()["paths"]
```

- La CLI y la API comparten código: la ruta siempre está en `app.openapi()` del propio proceso.
  `backend/tests/unit/test_cli.py:170-171` lo afirma (`is True`) y el test del bloqueo (`:174-181`)
  necesita `monkeypatch` para hacerla devolver `False`. La guarda es tautológica.
- Lo que sí puede fallar en producción no se mira: en `SettingsApi`, `baja_secret` es opcional
  (`config.py:68`, `SecretStr | None`) y sin ella `/baja/{token}` responde 404 a todo
  (`api/baja.py:14-16`, probado en `test_api_baja.py:94-98`). Si la API corre sin `BAJA_SECRET`, o con una
  clave distinta a la del entorno de la CLI, cada mail real sale con un enlace de baja y un
  `List-Unsubscribe` que dan 404.
- Escenario: `EMAIL_MODO=real` en la CLI, API en el PaaS sin `BAJA_SECRET` (es opcional, la API
  arranca igual). `enviar` manda hasta 20 mails; ningún destinatario puede darse de baja por el enlace.
  Es la regla "real bloqueado si no existe /baja/{token}" aplicada a la copia equivocada de la ruta.
- Guardas existentes que no lo atrapan: `model_validator` de `SettingsEmail` valida `API_BASE_URL`
  como https pero no la llama; `test_rutas_publicas_son_exactamente_estas` prueba el proceso de test.
- Recomendación: en modo real, antes de `armar_envio`, hacer un `GET {API_BASE_URL}/baja/{token}` con
  un token firmado para `(tenant, uuid4())` y exigir 200. GET no muta (`api/baja.py:26-31`) y solo
  responde 200 si la API tiene la misma clave: prueba a la vez que la ruta existe y que el secreto
  coincide. Si no responde 200, salir con código 2 y el mensaje actual. Reemplaza a
  `_hay_ruta_de_baja`, que puede borrarse.

### 2. `solicitudes` crece sin tope desde una ruta pública (bajo)

```sql
-- repositorio_contactos.py:73-75
UPDATE cumplimiento SET opt_out_at = COALESCE(opt_out_at, now()),
  solicitudes = solicitudes || jsonb_build_array(...)
WHERE lead_id = (SELECT lead_id FROM contactos WHERE id = :c)
```

- Quien tenga un token válido (el destinatario, o quien reenvíe el mail) puede hacer POST en bucle:
  cada llamada agrega ~70 bytes al JSONB de esa fila. No hay rate limit en `/baja/{token}` y la ruta es
  pública por diseño. El efecto es sobre una fila del propio tenant del token, no cruza tenants.
- Es bajo porque el token no se puede forjar (HMAC-SHA256, 128 bits) y el daño es una fila gorda, no
  pérdida de datos. `test_post_da_de_baja_y_es_idempotente` (`test_api_baja.py:62-68`) hoy espera dos
  entradas tras dos POST, o sea el crecimiento está codificado.
- Recomendación: anexar la solicitud solo si cambia algo (`WHERE ... AND opt_out_at IS NULL` en una
  segunda rama, o `CASE WHEN opt_out_at IS NULL THEN solicitudes || ... ELSE solicitudes END`), o un
  tope de entradas. Ajustar ese test. La monotonicidad ya la da `COALESCE` y no se toca.

### 3. `reclamar` pisa `base_legal` (bajo)

```python
# repositorio_contactos.py:49
c.execute(text("UPDATE cumplimiento SET base_legal = :bl WHERE lead_id = :l"), ...)
```

- Hoy nadie más escribe `base_legal` (`rg base_legal backend/app` solo da `modelos.py:120` y este
  módulo), así que no hay modo de falla real todavía. Cuando otro canal fije su propia base legal, este
  `UPDATE` la reemplaza en silencio por `persona_juridica_canal_publicado`.
- Recomendación: `SET base_legal = COALESCE(base_legal, :bl)`. Una línea, y `vigente` sigue exigiendo
  `base_legal IS NOT NULL` (`:56`).

### 4. `smtp_usuario` fuera de `SecretStr` (bajo)

- `config.py:83`: `smtp_usuario: str`. Con Resend el usuario es el literal `resend`
  (`tests/smtp_falso.py:7`), pero con SES o un relay genérico el usuario SMTP es un access key id.
  `repr(SettingsEmail)` lo muestra; `test_secretos_no_salen_en_repr` (`test_config_email.py:55-59`) solo
  comprueba clave y `BAJA_SECRET`. `email_prueba_destinos` también sale en el repr (direcciones propias
  de prueba, no de terceros: no es hallazgo).
- Recomendación: `smtp_usuario: SecretStr` y `.get_secret_value()` en `smtp_email.py:37`; sumar la
  aserción al test de repr.

### 5. Cupo diario recortado (info)

- `envio.py:13`: `TOPE_POR_CORRIDA = 20`, aplicado en `_seleccion` (`:52-56`) y probado
  (`test_envio_email.py:242-249`). El `max_por_dia_por_dominio` de la spec quedó fuera por decisión
  explícita (`tasks.md:90`, "Recortes 3"; `plan.md:180`). Correr `enviar` N veces el mismo día manda
  20·N. Se anota para que no se pierda antes de un envío real masivo; no es defecto del diff.

### 6. REVOKE condicionado a los dos roles (info)

- `0008_contactos.sql:46-48`: `IF EXISTS anon AND EXISTS authenticated THEN REVOKE ...`. Si existiera
  solo uno, no se revoca nada. En Supabase existen los dos y
  `test_la_migracion_cierra_sus_objetos_aunque_supabase_reabra_los_default_privileges`
  (`test_contactos_db.py:67-79`) prueba el caso real. Mismo patrón que la 0007. Cosmético.

### 7. GET 200 para contacto inexistente (info)

- `api/baja.py:27` solo verifica la firma; el POST (`:37`) además exige que el contacto exista. Un
  token firmado de un contacto borrado muestra el formulario y el POST da 404. No permite enumerar:
  sin la clave no hay token válido. Consistencia opcional, sin impacto de seguridad.

### 8. `enviar` real inalcanzable hoy (info)

- `cli.py:128-130`: `_armar_envio_postgres` lanza `NotImplementedError` hasta que exista el adaptador
  de leads contactables. Todo lo revisado del caso de uso se ejerce vía `armar_envio` inyectado en
  tests. La revisión del cableado real (qué `LeadsContactables` filtra "canal publicado") queda
  pendiente para ese merge.

## Verificado sin hallazgo, por foco

**1. Cumplimiento.**
- Solo jurídicas con cumplimiento y sin opt-out: `_ELEGIBLE` (`repositorio_contactos.py:12-13`)
  se evalúa en `crear` (`:35`), `reclamar` (`:45-46`) y `vigente` (`:52-57`). Tests
  `test_persona_natural_no_se_envia`, `test_sin_fila_de_cumplimiento_no_envia`, `test_con_opt_out_no_envia`.
- Canal publicado: lo decide el puerto `LeadsContactables` (`puertos.py:16-19`) más `ORIGENES` de la
  plantilla (`plantilla.py:6-9`, `:16-17`): un origen fuera de la lista no compone y no se crea contacto
  (`test_sin_canal_publicado_no_se_envia`).
- `base_legal` fijada al reclamar (`:49`) y exigida justo antes de mandar (`vigente`, `:56`);
  `test_envio_setea_base_legal`, `test_sin_base_legal_no_envia`.
- Reevaluación antes de mandar: `enviar` llama `reclamar` y `vigente` por contacto (`envio.py:109-113`);
  `test_baja_entre_reclamo_y_envio_gana`.
- BAJA monotónica: `COALESCE(opt_out_at, now())` (`:73`); `test_opt_out_es_monotonico`. Cierra todos
  los canales: por `lead_id`, no por contacto (`:78-82`), y la elegibilidad SQL de cualquier canal mira
  `opt_out_at`; `test_baja_cierra_todos_los_canales`.
- `EMAIL_MODO=prueba` por defecto (`config.py:93`); en prueba solo `email_prueba_destinos`, lista vacía
  = nada (`envio.py:54-55`; `test_modo_prueba_lista_vacia_no_manda`). La comparación es `!= "real"`:
  cualquier valor raro cae en prueba, y el `Literal` rechaza valores desconocidos.
- Tope 20 por corrida: `envio.py:13`, `:56`; `test_tope_20_por_corrida`.
- `enviar` exige `--dry-run` previo: `SinVistaPrevia` (`envio.py:94-95`); y frena si cambió
  `mensaje_base` antes de mandar nada (`:103-104`); `test_enviar_sin_dry_run_falla`,
  `test_mensaje_base_cambiado_frena`.

**2. Secretos y PII.**
- `SMTP_CLAVE` y `BAJA_SECRET` son `SecretStr` (`config.py:84`, `:88`); `hide_input_in_errors=True`
  en `Settings` (`:34`); la CLI imprime solo nombres (`cli.py:115-119`). Tests
  `test_secretos_no_salen_en_repr`, `test_secretos_no_salen_en_el_error_de_validacion`,
  `test_enviar_con_configuracion_invalida_imprime_solo_nombres`.
- Direcciones: `field(repr=False)` en `LeadContactable` y `MensajeSaliente` (`modelos.py:9`, `:21`);
  `CanalNoDisponible` solo con el nombre de la clase y `from None` (`smtp_email.py:45`);
  `DestinatarioInvalido` sin el valor (`:59`, `:64`); `hide_parameters=True` en el engine (`db.py:26`);
  el resumen del dry-run no lleva direcciones ni el token real (`envio.py:84-90`);
  `/baja` no refleja email ni ids. Ningún `logging`/`print`/`set_debuglevel` en el módulo
  (`rg` vacío). Tests `test_contacto_no_aparece_en_logs`, `test_dry_run_imprime_resumen_sin_direcciones`,
  `test_baja_no_expone_el_email`.
- Dirección no ASCII: comprobé en el intérprete que `send_message` lanza `SMTPNotSupportedError`
  (subclase de `SMTPException`, sin la dirección en el mensaje) antes de cualquier comando: cae en el
  `except` de `:41-45`.
- Repo y front: `git ls-files` solo rastrea `.env.example`; el diff del front es nulo; `rg` de
  `BAJA_SECRET|SMTP_CLAVE|/baja/` en `frontend/` no da nada. Las constantes de tests son
  evidentemente falsas (`re_test_X…`, `"b" * 32`).

**3. Aislamiento por tenant.**
- `contactos` con RLS y política `tenant_aislado` USING + WITH CHECK (`0008:25-28`); `app_rt` sin
  DELETE (`:29`); `test_rls.py` lo incluye en `TABLAS` y cubre UPDATE/DELETE/INSERT cruzados y las FK
  compuestas `(tenant_id, lead_id)`/`(tenant_id, busqueda_id)`.
- Vistas con `security_invoker = true` (`:31`, `:34`); `test_toda_vista_es_security_invoker` y
  `test_tenant_b_no_accede_a_datos_de_a_en_vistas` con control positivo.
- `anon`/`authenticated` sin privilegios: `test_privilegios_vistas` y el test que reabre los default
  privileges y reaplica la migración.
- Token de baja: el tenant viaja firmado (`tokens.py:15`); `DarDeBaja` abre el repo con ese tenant
  (`aplicacion/baja.py:20-21`) y cada consulta corre con `set_config('app.tenant_id', ..., true)`
  (`db.py:19`), así que un token de A no puede tocar filas de B aunque se pegue otro UUID
  (`test_otro_tenant_falla`). El engine de la API rechaza roles que saltean RLS (`db.py:31-41`).
- Las consultas del repo filtran por `id` y confían en RLS; es el patrón del resto del backend y el
  engine no acepta superusuario ni `BYPASSRLS`.

**4. `/baja/{token}`.**
- GET no muta: solo `verificar` (`api/baja.py:27`); `test_get_muestra_confirmacion_y_no_da_de_baja`.
- POST sin sesión ni cuerpo obligatorio: one-click RFC 8058 con `List-Unsubscribe-Post`
  (`smtp_email.py:74-75`); `test_one_click_rfc8058_sin_sesion`.
- Inválido = 404 idéntico al de FastAPI para firma rota, propósito `msgid`, otra clave y basura, en
  GET y POST (`test_token_invalido_404_generico`); sin `BAJA_SECRET`, 404 (`:15-16`).
- CSRF: el único efecto es el opt-out del contacto del token; quien tiene el token puede hacer POST
  directo. Sin cookies (`main.py:63`), nada que amplificar.
- XSS: el único dato reflejado es el token, solo tras verificar (alfabeto base64url) y además
  `html.escape(..., quote=True)` (`:29`). El `action` es relativo: sin host header injection.

**5. Tokens.**
- Propósito dentro del HMAC con separador `\0` (`tokens.py:11`): `msgid` no sirve como `baja`
  (`test_proposito_distinto_falla`, y en HTTP `test_token_invalido_404_generico`).
- `hmac.compare_digest` (`:28`; `test_compara_con_compare_digest`). Antes se comparan longitudes
  (`:25`), lo cual es aceptable: la longitud del token no es secreta.
- HMAC-SHA256 truncado a 16 bytes = 128 bits; clave `>= 32` caracteres (`config.py:68`, `:88`;
  `test_baja_secret_corta_no_arranca`). Sin caducidad: por diseño (el enlace del mail tiene que valer
  mientras exista el contacto) y la revocación es borrar el contacto o rotar la clave.

**6. Dependencias.** `pyproject.toml` solo agrega contratos de import-linter; `uv.lock` sin cambios.
`uv run pip-audit`: "No known vulnerabilities found" (Python 3.12.13, FastAPI 0.143.3, pydantic 2.14.1,
SQLAlchemy 2.1.5). El front no cambia en el diff.

**7. Concurrencia.** `reclamar` es un `UPDATE ... WHERE estado = 'aprobado' AND elegible RETURNING`
en una sola sentencia: dos corridas en paralelo reclaman una sola vez (`test_dos_envios_en_paralelo_mandan_uno`,
con barrera real). `crear` con `ON CONFLICT DO NOTHING` sobre `unique (tenant_id, lead_id, canal)`.
Fallo de QUIT tras DATA aceptado no reintenta (`smtp_email.py:41-45`).

## OWASP Top 10:2025, veredicto por categoría

| Categoría | Veredicto | Evidencia |
|-----------|-----------|-----------|
| A01 Broken Access Control | sin hallazgo (info 7) | RLS + tenant firmado en el token; `RUTAS_PUBLICAS` fijada por test (`test_auth.py:150-153`) |
| A02 Security Misconfiguration | info 6 | REVOKE condicionado; `SMTP_SEGURIDAD=ninguna` solo con host local (`config.py:106`); `API_BASE_URL` https salvo localhost (`:109-112`) |
| A03 Software Supply Chain | sin hallazgo | `pip-audit` limpio; sin dependencias nuevas |
| A04 Cryptographic Failures | bajo 4 | HMAC-SHA256, `compare_digest`, clave `>= 32`; `smtp_usuario` sin `SecretStr` |
| A05 Injection | sin hallazgo | SQL parametrizado; `_ELEGIBLE.format` solo interpola literales del propio código (`:35`, `:46`, `:57`); CR/LF en encabezados rechazado por `email.policy` (`smtp_email.py:60-64`); sobre SMTP con `to_addrs` explícito (`:39`) |
| A06 Insecure Design | medio 1, info 5 | Guarda de modo real sobre el proceso equivocado; cupo diario recortado |
| A07 Authentication Failures | sin hallazgo | La ruta pública es pública por diseño y lo único que autentica es la firma del token |
| A08 Software or Data Integrity | sin hallazgo | El cuerpo se recompone y compara antes de mandar (`envio.py:102-104`) |
| A09 Logging and Alerting | sin hallazgo | Sin logs en el módulo; los que hay en el resto no reciben direcciones. No hay alerta de abuso en `/baja` (ver bajo 2) |
| A10 Mishandling of Exceptional Conditions | bajo 2 | `solicitudes` sin tope; errores de transporte/destinatario separados y sin reintento del inválido (`test_destinatario_invalido_no_es_canal_no_disponible`) |

## Medido

- `git diff --stat origin/main...HEAD`: 43 archivos, +2409/−37.
- `uv run pytest tests/unit/contacto tests/unit/test_cli.py tests/unit/test_config_email.py tests/contratos/test_smtp_email.py`: 77 passed en 14 s.
- `uv run pip-audit`: sin vulnerabilidades conocidas.
- OWASP: `top10.owasp.org` redirige a la edición 2025; las diez categorías listadas arriba salen de esa página.
- Dirección no ASCII en `smtplib.SMTP.send_message` sin SMTPUTF8: `SMTPNotSupportedError`, `isinstance(..., SMTPException) == True`, la dirección no está en `str(e)`.

## No verificado

- Tests de integración (`tests/integration/test_api_baja.py`, `test_envio_email.py`, `test_contactos_db.py`,
  `test_rls.py`, `test_respuestas_manual.py`): necesitan Postgres de prueba; no los corrí en esta sesión.
  Los leí completos y la evidencia de arriba cita sus líneas.
- Entorno desplegado: si la API del PaaS tiene `BAJA_SECRET` y coincide con la de la CLI (es
  exactamente lo que el hallazgo 1 pide automatizar).
- Comportamiento real del proveedor SMTP con `List-Unsubscribe` one-click y con direcciones
  internacionalizadas (SMTPUTF8): solo contra el SMTP falso.
- `LeadsContactables` real (qué significa "canal publicado" en SQL): no existe en la rama (info 8).
