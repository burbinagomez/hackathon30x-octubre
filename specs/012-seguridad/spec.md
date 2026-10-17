# Spec 012 — Seguridad: sesión, límites, PII en logs, cabeceras y revisión

**Slice:** 012 · **Rama:** `feature/012-seguridad` · **Tiempo:** domingo PM (PRD §9, item 12: "cierre dom PM"; ≈ 6 h 35 completa, ≈ 5 h 15 con los cortes 1–4)
**Depende de:** 001 (CI, `verificar_entorno`, Caddy, `check_imagen`), 005 (auth, `api/cliente.ts`, rutas de búsqueda), 007 (`RUTAS_PUBLICAS`, `API_BASE_URL`), 008 (`calificaciones.exportado_en`, `/calificaciones/importar`), 009 (`/webhooks/whatsapp`, opt-in). 010 y 011 si entraron: sus rutas se suman a los límites. **Desbloquea:** 013.

> La 012 no agrega producto: cierra lo que la constitución (principios V y VI) exige y el 001 y la 005 dejaron abierto. El texto de la constitución **no cambia**: el principio V ya pide CodeQL, required checks y revisión `security` por PR. Lo que falta es implementarlos y probarlos. Cada medida nace con un test que hoy falla.

## Para quién
- **El jurado y Dapta:** ven un producto que maneja datos de contacto de empresas reales y lo hace con la sesión, los límites y las cabeceras de una app que podría salir a producción, no de una demo con el token en `sessionStorage`.
- **El equipo:** cierra los pendientes de seguridad que las specs anteriores derivaron a este slice, con un test por cada uno. Así "es seguro" pasa a ser un resultado de CI y deja de ser una frase del pitch.

## Qué hace
1. **Sesión: refresh token y access token fuera del storage.**
   - El access JWT dura 15 min y vive **solo en memoria**, en una variable del módulo `api/cliente.ts`. Nada queda en `sessionStorage` ni en `localStorage`.
   - El refresh es opaco y va en una cookie `HttpOnly` que JavaScript no puede leer.
   - La rotación es de un solo uso. La sesión tiene un tope absoluto de 8 h desde el login, y refrescar no lo extiende.
   - Se puede rotar `SESSION_SECRET` sin cortar las sesiones vivas.
2. **Proxy same-origin.** `up.railway.app` está en la Public Suffix List, así que `web` y `api` en subdominios de Railway son *cross-site*: una cookie que ponga la api no viajaría con `SameSite=Strict`. Caddy (servicio `web`) pasa `/api/*` a la api por la red privada de Railway, y la api queda **sin dominio público**.
3. **Rate limiting** en `/auth/sesion`, en las rutas que gastan créditos (`/busquedas/*`, `/intake/*`, `/calificaciones/importar`) y en el tamaño del body.
4. **Test de PII en logs transversal:** recorre todas las rutas de la app con canarios por columna del catálogo de sensibles y falla si alguno aparece en un log o en stdout. Cubre también los errores no manejados y los 422.
5. **Cabeceras en Caddy:** CSP estricta, HSTS, nosniff, Referrer-Policy, Permissions-Policy, COOP y sin `Server`. Las prueba un script en CI contra la imagen construida y un E2E contra el deploy.
6. **Lo del principio V que el 001 no tiene:**
   - CodeQL;
   - la lista de *required checks* de `main`, con el test de configuración que el principio V pide;
   - el job `revision-seguridad` con el agente `security` en cada PR;
   - un script para que el dueño del repo verifique la protección de rama y el secret scanning.
7. **Revisión del agente `security` sobre 002–008** (y sobre 009–011 si llegaron a `main` sin revisión por PR). El reporte queda en `docs/seguridad/`.
8. **Pantalla de cumplimiento** (`GET /cumplimiento`, delegada por la 005, la 008 y la 009). Por lead muestra razón social, fuentes, licencia, base legal, `as_of`, baja, opt-in de WhatsApp y `exportado_en`, más la tasa de bloqueo. **Sin email ni teléfono.** Es lo último del plan y lo primero del orden de corte.

## Puertos y adaptadores que toca (`config/fuentes.yaml`)
- **Sin entradas nuevas.** Ningún puerto nuevo, ningún adaptador nuevo. El limitador de rutas es infraestructura de la API (`backend/app/api/limites.py`), no una fuente: no tiene `habilitado` ni contrato de puerto.
- **`RegistroCostos`:** sin filas nuevas. La 012 no suma operaciones de salida del producto. Un 429 corta **antes** de tocar adaptadores, y por eso no hay costo que registrar: lo prueba `::test_429_no_toca_adaptadores_ni_costos`.

## Skills que aplican
- `cumplimiento-datos`: regla 9 (catálogo de sensibles, nunca en logs), regla 5 (fila en `cumplimiento`, que la pantalla nueva muestra) y regla 11 (atribución, sin cambios).
- `libro-costos`: solo para confirmar que un 429 no deja fila y que el job de CI no es operación del producto (ver Decisiones técnicas).
- `slice-tdd`.

## Evals
Sin evals nuevos: la 012 no suma componentes con LLM al producto. El job `revision-seguridad` usa Claude en CI, pero su salida no es del producto ni se mide con umbral: es un gate binario (`Veredicto`). Los evals que otras specs derivaron acá (007 corte 4, 008 corte 3, 009 corte 3) **no entran** (ver Fuera del alcance).

## Flujo principal
1. **Login:** `POST /api/auth/sesion {email, clave}`.
   - Caddy saca el prefijo y la api recibe `/auth/sesion`.
   - La api exige `Origin == WEB_ORIGIN` (si no, 403): es la ruta que pone la cookie, y así un sitio ajeno no puede loguear al usuario en otra cuenta (login CSRF).
   - Antes de calcular scrypt, el limitador mira los fallos de ese email. Con 5 fallos en 15 min responde 429 con `Retry-After`, la misma respuesta exista o no el email.
   - Si pasa el límite, un semáforo global admite 2 scrypt a la vez. Quien espera más de 5 s recibe 503 con `Retry-After`.
   - Con la clave correcta, la api:
     1. crea una familia de refresh;
     2. guarda solo el `sha256` del token;
     3. devuelve `{access_token, expira_en}`, con el `exp` del access en `min(ahora + 15 min, familia.expira_en)`;
     4. pone `Set-Cookie: __Secure-refresco=<32 bytes base64url>; HttpOnly; Secure; SameSite=Strict; Path=/api/auth; Max-Age=28800`. En cada rotación, `Max-Age` son los segundos que faltan hasta `familia.expira_en`, no 28800 fijo.

     Un login exitoso resetea el contador de fallos.
2. **Uso normal:** el front manda `Authorization: Bearer <access>` desde memoria. La cookie no viaja a esas rutas, porque su `Path` es `/api/auth`.
3. **Access vencido o recarga de la página:** el front llama `POST /api/auth/refrescar`, con un solo pedido en vuelo por pestaña.
   - La api exige `Origin == WEB_ORIGIN` (si no, 403) y busca el hash.
   - Si el token está vigente y no fue usado, lo marca usado, emite uno nuevo de la misma familia (con el mismo `expira_en` absoluto) y un access nuevo.
   - Si ya fue usado hace ≤ 10 s, responde 409 `refresco_en_curso` y el front reintenta una vez: es la carrera de dos pestañas.
   - Si ya fue usado hace > 10 s, es reuso: revoca **toda la familia** y responde 401.
4. **Un 401 en una ruta con sesión:** el front refresca una vez y reintenta el pedido original. Si el refresh falla, borra el access de memoria y va a `/login`.
5. **Salir:** `POST /api/auth/salir` (mismo chequeo de `Origin`) revoca la familia y responde con `Set-Cookie` y `Max-Age=0`.
6. **Rutas que gastan:**
   - Antes del caso de uso, el limitador por `tenant_id` del token cuenta en ventana deslizante de 1 h.
   - Si se pasa, responde 429 con `Retry-After` y no llama al caso de uso: no hay adaptador ni `costos`.
   - Caddy corta cualquier body de más de 1 MB con 413 antes de llegar a la api.
7. **CI en un PR:**
   - `back`, `front`, `seguridad`, `evals` e `imagenes` (que ahora también corre `check_cabeceras`);
   - `codeql` (python y javascript-typescript);
   - `revision-seguridad`: el agente `security` sobre el diff, que bloquea si no encuentra `Veredicto: PASA` o `Veredicto: PASA CON OBSERVACIONES`.

   Todos son *required checks* de `main`.

## Terminado cuando (tests que hoy fallan)

**Sesión — dominio** (`backend/tests/unit/acceso/test_refresco.py`, puro, reloj inyectable)
- `::test_rotar_emite_token_nuevo_de_la_misma_familia`: rotar un token vigente lo marca usado y devuelve otro con la misma `familia` y el mismo `expira_en` absoluto.
- `::test_reuso_dentro_de_la_gracia_da_en_curso`: el mismo token rotado dos veces en 10 s da `RefrescoEnCurso` la segunda vez, y la familia sigue viva.
- `::test_reuso_fuera_de_la_gracia_revoca_la_familia`: a los 11 s da `RefrescoReusado`, y todos los tokens de la familia quedan revocados, incluido el último emitido.
- `::test_tope_absoluto_de_8_horas`: a las 8 h y 1 s del login, rotar da `SesionVencida` aunque el token no se haya usado nunca.
- `::test_access_no_vive_mas_que_la_familia`: rotar a las 7 h 59 min emite un access con `exp` = `familia.expira_en` (1 min), no 15 min, y una cookie con `Max-Age=60`.
- `::test_solo_se_guarda_el_hash`: el repositorio falso recibe `sha256(token)`, nunca el token.

**Sesión — API** (se suma a `backend/tests/integration/test_auth.py`, Postgres de prueba, rol `app_rt`; el cliente usa `base_url="https://testserver"`, porque httpx no manda cookies `Secure` por `http://` y los tests fallarían por la razón equivocada)
- `::test_sesion_pone_cookie_de_refresco_con_atributos`: el `Set-Cookie` trae exactamente `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth` y `Max-Age=28800`, con el prefijo `__Secure-`. **Reemplaza** a `test_sesion_con_clave_correcta_devuelve_token` de la 005: el access dura 15 min, ya no 8 h.
- `::test_refrescar_rota_y_devuelve_access_nuevo`.
- `::test_sin_origin_o_con_otro_origin_da_403[ruta-caso]`: `/auth/sesion`, `/auth/refrescar` y `/auth/salir`, cada una sin `Origin`, con `Origin: https://otro.example` y con `Origin: null`.
- `::test_refrescar_con_token_reusado_revoca_la_familia`.
- `::test_refrescar_dentro_de_la_gracia_da_409_en_curso`.
- `::test_dos_refrescos_simultaneos_dan_un_ok_y_un_en_curso`: dos conexiones llaman `rotar_refresco` con el mismo hash a la vez (barrera con `asyncio.gather`). Sale exactamente 1 `ok` y 1 `en_curso`, nunca 2 `ok`. Es lo que justifica el `FOR UPDATE`, y nace rojo si la función no lo tiene.
- `::test_salir_revoca_y_borra_la_cookie`: después de salir, el refresh viejo da 401.
- `::test_app_rt_no_lee_sesiones_refresco`: `SELECT` directo sobre `sesiones_refresco` como `app_rt` da 0 filas o permiso denegado. Solo las funciones `SECURITY DEFINER` la tocan, con el mismo patrón que `usuario_para_login` (005).
- `::test_access_firmado_con_secret_anterior_se_acepta`: con `SESSION_SECRET_ANTERIOR` seteado, un access firmado con él valida, y uno nuevo se firma con `SESSION_SECRET`.
- `::test_app_no_arranca_con_secret_anterior_debil_o_igual[caso]`: < 32 bytes o igual a `SESSION_SECRET` → `verificar_entorno` corta, nombrando la variable y nunca el valor.
- `backend/tests/integration/test_api_auth.py::test_rutas_publicas_son_exactamente_estas` (007, 009): la lista suma `/auth/refrescar` y `/auth/salir`.

**Rate limiting** (`backend/tests/unit/api/test_limites.py`, reloj inyectable, y `backend/tests/integration/test_api_limites.py`)
- `::test_ventana_deslizante_cuenta_solo_la_ultima_hora`.
- `::test_quinto_fallo_bloquea_el_sexto_intento_sin_scrypt`: con un `hash_clave` espía, el sexto intento da 429 con `Retry-After`, y el espía tiene 5 llamadas, no 6.
- `::test_429_de_login_es_igual_exista_o_no_el_email`: mismo status, mismo body y mismas cabeceras (salvo `Retry-After`, que es por email).
- `::test_login_exitoso_resetea_el_contador`.
- `::test_tercer_scrypt_concurrente_espera_y_a_los_5s_da_503`.
- `::test_limite_por_tenant[ruta]`: `vista-previa` 30/h, `ejecutar` 10/h, `intake/lookalike` 5/h, `intake/frase` 20/h y `calificaciones/importar` 10/h. El intento n+1 da 429, y otro tenant en la misma ventana pasa.
- `::test_429_no_toca_adaptadores_ni_costos`: con adaptadores falsos espía, el 429 deja 0 llamadas y 0 filas nuevas en `costos`.
- `::test_limites_no_usan_la_ip`: dos pedidos del mismo tenant con `client=` distinto en el `TestClient` (y `X-Forwarded-For` distinto) comparten el contador. Variar solo la cabecera no alcanza: un limitador por `request.client` también pasaría.
- `::test_las_claves_vacias_se_borran`: después de que la ventana de 10.000 emails distintos vence, el diccionario del limitador queda vacío. Si no, alguien que prueba emails al azar hace crecer la memoria sin tope.

**PII en logs, transversal** (`backend/tests/integration/test_pii_en_logs.py`)
- `::test_catalogo_tiene_canario_por_columna`: cada columna de `catalogo_sensibles.py` tiene un valor canario en `CANARIOS`, claramente falso (`canario-pii@ejemplo.invalid`, `+576015550100`, `Nombre Canario Prueba`, `respuesta canario xyzzy`). Una columna nueva sin canario hace fallar el test.
- `::test_ninguna_ruta_filtra_contacto_a_logs[ruta]`:
  - Se parametriza sobre `app.routes`. Cada ruta tiene un caso en `CASOS_PII` (pedido que mete los canarios en el body, la query o el estado previo de la base) o una exención con motivo escrito (`/health`: no recibe datos).
  - Una ruta sin caso ni exención hace fallar el test: así una ruta nueva no puede entrar sin pasar por acá.
  - Captura con `caplog` en DEBUG sobre root y `httpx`, más `capsys`. Falla si algún canario aparece, en claro o en base64. `uvicorn.access` no se captura acá porque `TestClient` no corre uvicorn: lo cubre `::test_api_arranca_sin_access_log`.
- `::test_error_no_manejado_no_filtra_contacto`:
  - Una ruta de prueba lanza `ValueError(canario_email)` y otra lanza un `ValidationError` de pydantic con `input_value=canario_telefono`. Las dos dan 500 genérico `{"error": "interno"}`, y el log trae solo el tipo de excepción y la ruta.
  - El `TestClient` usa `raise_server_exceptions=True`, y el test verifica que **la excepción no sale de la app**. Con `@app.exception_handler(Exception)` el test daría verde con la fuga puesta: Starlette lo atiende en `ServerErrorMiddleware`, que responde y después vuelve a lanzar, y en producción uvicorn loguea el traceback con `str(exc)`, o sea el canario.
- `::test_422_no_devuelve_ni_loguea_el_input`: un body inválido con los canarios da 422, ningún log trae el `input`, y **el body de la respuesta tampoco**. Hoy FastAPI devuelve `input` en el 422, así que este assert nace rojo.
- `backend/tests/arquitectura/test_secrets.py::test_api_arranca_sin_access_log`: el `CMD` de `backend/Dockerfile` lleva `--no-access-log`.
- `::test_corrida_programada_no_filtra_contacto`: `EnviarAprobados` (007), `ClasificarRespuestasPendientes` (007) y el poll IMAP, con fakes y los canarios en la base, no dejan ningún canario en los logs.
- No reemplaza a `test_contacto_no_aparece_en_logs` (003) ni al fixture regex de la 004: esos prueban su módulo, y este prueba que **ninguna** ruta se escape.

**Cabeceras** (`.github/scripts/check_cabeceras.sh` + `.github/scripts/test_check_cabeceras.sh`, mismo patrón que `check_imagen`)
- El script levanta la imagen `web` en una red docker con un upstream stub (`python:3.12-alpine python -m http.server 8000`) como `API_UPSTREAM`, y verifica:
  - en `/`: CSP exacta, HSTS, `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin` y **sin** `Server`;
  - en `/api/`: lo mismo más `Cache-Control: no-store`. Cubre la página HTML de `/api/baja/{token}` (007), que ahora pasa por la CSP de Caddy;
  - un POST de 2 MB a `/api/x` da 413.
- `test_check_cabeceras.sh`: corre el script contra un Caddyfile al que le falta la CSP y espera salida ≠ 0. Un check que no puede fallar no prueba nada.
- `backend/tests/arquitectura/test_secrets.py::test_dockerfile_web_no_recibe_args` (001): reemplaza a `test_dockerfile_web_solo_recibe_vite_api_url`. Con `/api` relativo, `frontend/Dockerfile` no declara ningún `ARG`, y ninguna variable de Railway llega al bundle.

**Front** (Vitest)
- `frontend/src/api/cliente.test.ts::el_access_no_toca_el_storage`: después del login, `sessionStorage` y `localStorage` están vacíos.
- `::un_401_refresca_una_vez_y_reintenta`: reemplaza a `un_401_lleva_al_login_y_borra_el_token` (005). Un 401 lleva a 1 refresh y 1 reintento; si el refresh da 401, el front va a `/login`.
- `::dos_401_simultaneos_hacen_un_solo_refresh`: single-flight.
- `::un_409_en_curso_reintenta_el_refresh_una_vez`.
- `::al_cargar_restaura_la_sesion_con_refrescar`.
- `::usa_api_relativo`: todas las llamadas van a `/api/...`, sin host.

**E2E** (`frontend/e2e/seguridad.spec.ts`, en `e2e.yml` contra el deploy, con `E2E_EMAIL` y `E2E_CLAVE` como secrets)
- `::navegar_no_viola_la_csp`: login → tablero → NuevaBusqueda → Mensajes, y `/api/baja/{token}` con un token de prueba (`E2E_TOKEN_BAJA`, de un lead sintético), con 0 eventos `securitypolicyviolation`.
- `::recargar_mantiene_la_sesion`.
- `::el_storage_queda_vacio`.
- `::la_api_no_tiene_dominio_publico`: con `E2E_API_PUBLICA` (el dominio viejo de Railway, si existió), la conexión falla o da 404 de Railway. Si la variable no está, el test se salta con el motivo escrito.

**Configuración del repo** (`backend/tests/arquitectura/test_required_checks.py`)
- `::test_cada_check_requerido_existe_como_job`:
  - La protección de rama compara **nombres de check-run**, no ids de job. El test los deriva de los workflows igual que GitHub: el `name:` del job (o su id si no tiene), y para una matriz, `"{nombre} ({valor})"`, como `codeql (python)`.
  - Cada nombre de `.github/required-checks.txt` coincide con un check-run derivado.
  - Cada job de `ci.yml` y `codeql.yml` que corre en `pull_request`, salvo `migrar`, está en la lista.
  - Un job nuevo que no se suma a la lista, una lista que nombra un job borrado o un `name:` que cambia hacen fallar el test.
- `::test_constitucion_v_tiene_su_step`:
  - `dependabot.yml` tiene los 4 ecosistemas (uv, npm, github-actions, docker);
  - `ci.yml` corre `pip-audit`, `npm audit --audit-level=high` y gitleaks (repuesto por la 012, ver Decisiones técnicas). Nace rojo en `main`, porque el step no está;
  - `codeql.yml` analiza `python` y `javascript-typescript`;
  - `revision-seguridad` existe y corre solo en `pull_request`.
- `::test_revision_seguridad_es_fail_closed`: el script de parseo del veredicto (`.github/scripts/veredicto_security.sh`) sale 0 solo con una línea exacta `Veredicto: PASA` o `Veredicto: PASA CON OBSERVACIONES`. Con `BLOQUEA`, sin línea, con salida vacía, con el veredicto dentro de un bloque de código o con dos líneas `Veredicto:` (aunque una diga `PASA`), sale ≠ 0.
- `.github/scripts/verificar_proteccion.sh`: no es test de CI, porque el token de Actions no tiene permiso de admin. Lo corre el dueño del repo y compara `gh api repos/{o}/{r}/branches/main/protection` contra `required-checks.txt`, con `security_and_analysis.secret_scanning` y `secret_scanning_push_protection` en `enabled`. La salida se pega en `docs/seguridad/revision-002-008.md`.

**Pantalla de cumplimiento** (último del plan)
- `backend/tests/integration/test_api_cumplimiento.py::test_cumplimiento_lista_por_lead_sin_contacto`: la respuesta trae razón social, fuentes, licencia, `base_legal`, `as_of`, `opt_out_at`, opt-in de WhatsApp y `exportado_en`, y ningún campo del catálogo de sensibles. El canario de email no aparece en el body.
- `::test_cumplimiento_trae_tasa_de_bloqueo`.
- `::test_cumplimiento_es_por_tenant`: otro tenant da lista vacía (RLS).
- `frontend/src/cumplimiento/Cumplimiento.test.tsx::muestra_fuente_licencia_y_baja_por_lead`.

## Fuera del alcance
- **Lo derivado a la 012 que no es seguridad:** el E2E de búsqueda (005 corte 2, 011), la cobertura por país y las revisiones pendientes del tablero (005 corte 5), los evals de 007, 008 y 009 (`match_dapta` incluido) y la rama `meta` de la 009. Si se cortaron, quedan cortados, y la 013 los lista en "qué es real y qué es simulado". No se esconden.
- **Retención y purga** (regla 10 de `cumplimiento-datos`): sigue documentada y sin job.
- **Cambiar el texto de la constitución:** no hace falta (ver Decisiones técnicas).
- **Rate limit por IP:** detrás de Railway y Caddy la IP real no se puede validar, y un límite por IP equivocado sería global.
- **Rate limit del webhook de WhatsApp:** sin contador. La firma HMAC se verifica antes de parsear, y Caddy corta el body a 1 MB. Una firma inválida cuesta un HMAC, y las válidas solo las puede mandar Meta.
- **Rate limit de `/auth/refrescar`:** el token es de 32 bytes aleatorios y la búsqueda es un `sha256`. Adivinarlo no es viable, y cada intento cuesta lo mismo que un 404.
- **MFA, recuperación de clave, alta de usuarios:** siguen fuera, como en la 005.
- **WAF, protección DDoS:** lo que Railway dé. Nada propio.

## Decisiones técnicas

**Principio V, sin cambio de texto.** Ya pide CodeQL, required checks, secret scanning y revisión `security` por PR. El 001 implementó dependabot, `pip-audit`, `npm audit` y `verificar_entorno`. Gitleaks también estaba, pero se quitó el 17-oct (`02c940d`, "ya lo cubre GitHub Advanced Security"), y la 012 lo repone (ver **Gitleaks**). **No implementó CodeQL** (verificado: no hay `codeql.yml` en `.github/`), ni la lista de required checks con su test, ni la revisión `security` en CI. La 012 los agrega. No toca la constitución ni ninguna migración existente.

**Proxy same-origin en Caddy:**
```
handle_path /api/* {
	request_body { max_size 1MB }
	header Cache-Control "no-store"
	reverse_proxy {$API_UPSTREAM}
}
```
- `API_UPSTREAM` = `api.railway.internal:8000` en Railway. Si la red privada del proyecto resulta ser solo IPv6, el `CMD` de la api pasa a `--host ::` `# [VALIDAR]` al crear el entorno.
- La api queda sin dominio público: se borra el dominio generado en Railway.
- `API_BASE_URL` (007) pasa a `{WEB_BASE_URL}/api`. El enlace de baja y `List-Unsubscribe` siguen apuntando a la api, a través del proxy. `test_headers_list_unsubscribe_y_message_id` (007) cambia "el host es el de `API_BASE_URL`" por "el path empieza con `/api/baja/`".
- El webhook de Meta (009) se registra en `https://<web>/api/webhooks/whatsapp`.
- `VITE_API_URL` desaparece: el front usa `/api` relativo, y en dev usa el `server.proxy` de Vite.
- `CORS_ORIGINS`/`WEB_ORIGIN` siguen igual de restringidos, sin `allow_credentials`. Same-origin no necesita CORS, y dejarlo cerrado no rompe nada.
- La api **no** activa `--proxy-headers`: ningún código usa la IP del cliente.

**Cookie y CSRF.**
- `SameSite=Strict` y `Path=/api/auth` hacen que la cookie solo viaje a refrescar y salir, y solo desde el propio sitio.
- El chequeo de `Origin == WEB_ORIGIN` en las tres rutas de `/auth` es la segunda capa, para navegadores viejos o un `SameSite` mal aplicado. En `/auth/sesion` cierra además el login CSRF.
- El resto de las rutas usa `Authorization: Bearer` desde memoria: un formulario de otro sitio no puede mandarlo, así que no hay CSRF.
- El XSS ya no puede robar una sesión de 8 h: como mucho usa un access de 15 min mientras la pestaña está abierta. La CSP lo acota además.

**`sesiones_refresco` (migración nueva del slice, `00XX_sesiones_refresco`, en el formato de migraciones que esté en `main` al empezar: hoy Alembic, o SQL del Supabase CLI si el 001 lo migró):**
- Columnas: `id`, `usuario_id`, `tenant_id`, `familia uuid`, `hash bytea UNIQUE`, `expira_en`, `usado_en`, `revocado_en` y `creado_en`.
- RLS activada **sin policies** para `app_rt`: el rol no la lee ni la escribe directo.
- Funciones `SECURITY DEFINER` con dueño `app_mig`, `SET search_path = public, pg_temp`, `REVOKE` a `PUBLIC`/`anon`/`authenticated` y `GRANT EXECUTE` solo a `app_rt`, igual que `usuario_para_login`:
  - `crear_refresco(usuario_id, tenant_id, hash, expira_en)`;
  - `rotar_refresco(hash_viejo, hash_nuevo, ahora, gracia)`, que devuelve el estado (`ok`, `en_curso`, `reusado` o `vencido`) y hace el `FOR UPDATE` sobre la fila;
  - `revocar_familia(hash)`.
- La regla de gracia y reuso vive en dominio (`acceso/dominio/refresco.py`), y la función SQL solo la ejecuta atómicamente. Los tests de dominio la prueban sin base.
- Esta spec **solo describe** la migración: se escribe en el slice, con su test rojo, no en este PR de specs.

**Rotación de `SESSION_SECRET`.**
- `SESSION_SECRET_ANTERIOR` es opcional y sirve solo para verificar, nunca para firmar.
- Para rotar: se mueve el secret actual a `_ANTERIOR`, se pone uno nuevo, se redeploya y, a los 15 min (lo que dura un access), se borra `_ANTERIOR`.
- Los refresh no dependen del secret: son opacos y van hasheados en la base.

**Rate limiting en memoria.**
- `backend/app/api/limites.py`: una ventana deslizante con `collections.deque` por clave y un `asyncio.Semaphore(2)` para scrypt. Es stdlib, sin dependencia nueva.
- `# ponytail: en memoria, asume 1 worker y 1 réplica (CMD actual de uvicorn); con más réplicas, contador en Postgres`.
- Las claves son `login:{email_normalizado}` y `tenant:{tenant_id}:{ruta}`. Nunca la IP.
- El email normalizado va como clave en memoria y **nunca** se loguea: el test de PII lo cubre con el canario.
- Cada chequeo descarta lo vencido de su deque, y una deque que queda vacía se borra del diccionario. Así la memoria la acota la ventana, no la cantidad de emails que alguien pruebe.
- **Riesgo aceptado:** alguien que conozca el email de la demo puede bloquearle el login 15 min con 5 intentos. Para un evento con un usuario por tenant es preferible a dejar que alguien adivine claves.
- **Riesgo aceptado:** alguien que pruebe muchos emails distintos a la vez llena el semáforo de scrypt, y el usuario legítimo recibe 503 mientras dure. Es el precio de no quedarse sin memoria (005, scrypt ~128 MiB por login).

**CSP y cabeceras** (bloque `header` global en el Caddyfile, más `-Server`):
```
Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
Strict-Transport-Security "max-age=31536000; includeSubDomains"
X-Content-Type-Options "nosniff"
Referrer-Policy "no-referrer"
Permissions-Policy "camera=(), microphone=(), geolocation=()"
Cross-Origin-Opener-Policy "same-origin"
```
- `style-src 'self'` sin `'unsafe-inline'` exige que el front no use atributos `style=` inline.
- Si React o alguna librería de la 005 los usa, el E2E `navegar_no_viola_la_csp` lo detecta. Se corrige el componente; la CSP no se afloja. Si no hay forma, se agrega el hash puntual con un comentario.
- El pie de atribución (005) enlaza a openstreetmap.org con un `<a>`, y eso no es `connect-src`.
- Caddy queda **sin log de acceso**: no hay nada que filtrar, porque el body nunca se loguea y la query de `/api/baja/{token}` no tiene contacto, pero así tampoco hay nada que revisar.

**CodeQL** (`.github/workflows/codeql.yml`): `github/codeql-action` pinneado por SHA, con la matriz `python` y `javascript-typescript`, en `pull_request` y `push` a `main`. El repo es **público** (verificado con `gh repo view`), así que CodeQL, secret scanning y push protection no necesitan GHAS pago.

**Gitleaks, repuesto.** Se quitó el 17-oct (`02c940d`) bajo el supuesto de que GitHub secret scanning lo cubre, y no lo cubre. Secret scanning y push protection detectan **patrones de proveedores**: tokens de Anthropic, de GitHub, de Stripe. No detectan un `DATABASE_URL` con password de Supabase, un `SESSION_SECRET`, la clave de cifrado del contacto ni un HMAC de webhook, y esos son justo los secrets de este proyecto. El paso se repone igual que estaba antes de `02c940d`:
- `GITLEAKS_VERSION` fija, con la descarga verificada por `sha256sum` contra el `checksums.txt` del release;
- el rango del PR (`base..head`) o del push, y todo el historial en rama nueva;
- `--redact` para que el log de CI no imprima el secret encontrado.

Va en el job `seguridad`, que ya es required check. No se reemplaza por otra herramienta: es la que ya estaba probada.

**`revision-seguridad`** (job nuevo en `ci.yml`, solo en `pull_request`):
- Corre `claude -p` en modo headless, con la CLI pinneada a una versión exacta `# [VALIDAR]` la del día.
- El prompt es el del agente `security` (`.claude/agents/security.md`) sobre `git diff ${BASE}..${HEAD}`.
- Usa `--allowedTools Read,Grep,Glob`: **sin Bash, sin red y sin escritura**. Un diff con prompt injection puede, como mucho, torcer el veredicto. No puede exfiltrar `ANTHROPIC_API_KEY` ni tocar el repo.
- Es fail-closed: `veredicto_security.sh` pasa solo con la línea exacta (ver Terminado cuando). El reporte completo queda como artefacto del job y en el summary.
- `ANTHROPIC_API_KEY` es de una **cuenta nueva del evento** (CLAUDE.md: nada de otros proyectos), como secret del repo.
- Los PRs desde forks no reciben secrets y el job falla cerrado. Es aceptable: en el evento no hay forks.
- **Costos.** El principio VIII dice "cada llamada a LLM", y la 004 hace que los jueces de evals escriban en `costos` con `fuente='evals'`. Por eso el criterio queda escrito:
  - VIII cubre los **componentes del producto**, los que corren dentro de la app con un `tenant_id` (clasificador, redactor, ICP de la 010, jueces de eval).
  - Las **herramientas de desarrollo** quedan afuera: el harness de Claude Code con el que se construye y este job de CI. No los dispara un tenant ni salen hacia un lead.
  - Escribir el job en `costos` exigiría credenciales de la base de producción en un job de PR, que es peor que no registrarlo.
  - Para que el gasto no quede oculto, el job publica `total_cost_usd` de la salida JSON en el summary, y la 013 reporta el gasto de CI aparte del CPL y el CPQL, leído de la consola de la cuenta del evento.

**Handler global de errores.**
- Es un middleware HTTP propio (`@app.middleware("http")` con `try/except Exception`) que arma el 500 `{"error": "interno"}` y loguea `type(exc).__name__` y la ruta, sin `str(exc)` ni traceback con locals.
- **No** es `@app.exception_handler(Exception)`: Starlette lo atiende en `ServerErrorMiddleware`, que responde y después vuelve a lanzar, y uvicorn loguea el traceback completo.
- El handler de `RequestValidationError` responde el 422 con los `loc` y `type` de pydantic, sin `input` ni `ctx`, y no loguea el body.
- El `CMD` de la api suma `--no-access-log`: la línea de acceso de uvicorn trae el path con la query, y no hace falta para nada.

**Pantalla de cumplimiento.** La consulta vive en el adaptador del repositorio de leads, como un `SELECT` sobre `leads`, `cumplimiento`, `calificaciones` y la tasa de bloqueo de la 009, sin vista nueva. Si no alcanza el tiempo, es lo primero que se corta, porque los datos ya existen y se pueden mostrar por SQL en la demo.

## Plan de tareas (TDD, en orden)
0. **Precondición:** 002–008 mergeadas a `main` (009–011 si llegaron). Sin código de back en `main`, los pasos 2–8 no tienen contra qué correr.
1. **Revisión `security` sobre 002–008 (≈ 35 min):** el agente corre sobre `git diff <tag-001>..main` por slice y deja el reporte en `docs/seguridad/revision-002-008.md`. Un CRITICAL o HIGH se arregla acá, con su test rojo, o bloquea el cierre del slice. Va primero porque puede cambiar el resto del plan.
2. **Config del repo (≈ 40 min):** rojo `test_required_checks.py` → `required-checks.txt`, `codeql.yml`, el step de gitleaks repuesto y `veredicto_security.sh` con su test → job `revision-seguridad` → verde. El dueño corre `verificar_proteccion.sh` y configura la protección de `main` con esa lista.
3. **PII transversal (≈ 40 min):** rojo `test_pii_en_logs.py` y `test_api_arranca_sin_access_log`. Con las rutas existentes deberían fallar al menos `::test_error_no_manejado_no_filtra_contacto` (no hay middleware) y `::test_422_no_devuelve_ni_loguea_el_input` (FastAPI devuelve `input`) → middleware de errores, handler de 422 y `--no-access-log` → verde. Si alguna ruta filtra, se arregla en su módulo.
4. **Proxy same-origin y deploy (≈ 60 min).** Va antes que la sesión porque la cookie depende de él.
   - Rojo `check_cabeceras.sh` (sin `/api` ni cabeceras) y `test_check_cabeceras.sh` → Caddyfile con `handle_path`, cabeceras y `request_body` → verde.
   - En el mismo paso: `test_dockerfile_web_no_recibe_args` en rojo → sacar el `ARG` → verde, y `cliente.test.ts::usa_api_relativo`.
   - Deploy en Railway: `API_UPSTREAM` en `web` (probar la red privada y el `--host ::` acá), `API_BASE_URL` nuevo en `api`, borrar el dominio público de la api y cambiar la URL del webhook en Meta, si la 009 la registró.
   - Correr `e2e.yml` con `::navegar_no_viola_la_csp` contra el deploy. Si la CSP rompe algo, se sabe acá y no al final.
5. **Sesión — dominio (≈ 20 min):** rojo `test_refresco.py` → `acceso/dominio/refresco.py` → verde.
6. **Sesión — base y API (≈ 50 min):** migración `00XX_sesiones_refresco` → rojo los tests de `test_auth.py` (concurrencia incluida) y `test_rutas_publicas_son_exactamente_estas` → rutas `/auth/refrescar`, `/auth/salir`, `Origin` y cookie en `/auth/sesion` → verde. `SESSION_SECRET_ANTERIOR` en `verificar_entorno`.
7. **Sesión — front (≈ 35 min):** rojo `cliente.test.ts` (los 6) → access en memoria, single-flight, restaurar al cargar → verde.
8. **Rate limiting (≈ 40 min):** rojo `test_limites.py` y `test_api_limites.py` → `limites.py` y la dependencia FastAPI en cada ruta → verde.
9. **E2E de sesión (≈ 15 min):** el resto de `seguridad.spec.ts` contra el deploy (recargar, storage vacío, api sin dominio público).
10. **Pantalla de cumplimiento (≈ 45 min):** rojo `test_api_cumplimiento.py` y `Cumplimiento.test.tsx` → verde.
11. **Doc (≈ 15 min):** `docs/arquitectura-backend.md` (sesión, límites, handler) y `-frontend.md` (cliente sin storage, `/api` relativo), más `.env.example` (suma `SESSION_SECRET_ANTERIOR` y `API_UPSTREAM`, saca `VITE_API_URL`).

## Riesgos
- **La red privada de Railway no resuelve como se espera** (IPv6, nombre del servicio): el proxy no llega a la api y nada funciona. Mitigación: el deploy es parte del paso 4, antes de construir la sesión, y se prueba primero en un entorno de staging de Railway. Si falla y no hay tiempo, se vuelve al dominio público de la api con `VITE_API_URL`, y la cookie de refresh se cae. En ese caso el access de 15 min queda en memoria y recargar pide login. Se documenta como degradación en la 013.
- **La CSP rompe algo que los tests unitarios no ven** (un estilo inline de una librería): lo detecta el E2E contra el deploy, no antes. Mitigación: el E2E de CSP corre apenas está el proxy (paso 4) y no al final.
- **`revision-seguridad` da falsos BLOQUEA** y frena PRs el domingo: el reporte dice por qué, y un humano corrige el código o, si es un falso positivo, lo anota en el PR y lo re-corre. **No** se saca el check de la lista de requeridos para destrabar.
- **Prompt injection en el diff** tuerce el veredicto a PASA: sin herramientas de escritura ni red no puede hacer otra cosa. Es la razón por la que el gate es una capa más y no la única (CodeQL, gitleaks y los tests siguen).
- **El semáforo de scrypt y los contadores asumen un proceso:** si alguien sube réplicas o workers en Railway, los límites se multiplican sin aviso. Mitigación: el comentario `ponytail:` en `limites.py` y una línea en `docs/arquitectura-backend.md`.
- **Bloqueo de la cuenta de la demo por intentos fallidos, o 503 por el semáforo de scrypt lleno** (riesgos aceptados, ver Decisiones técnicas): si pasa en el pitch, se espera 15 min o se reinicia la api, que vacía el contador en memoria.
- **El paso 1 encuentra un HIGH grande en un slice viejo:** se come el tiempo de los pasos 8–10. El orden de corte lo absorbe. Un HIGH sin arreglar bloquea el cierre igual (principio V).

**Orden de corte**, si no alcanza el tiempo:
1. **10, la pantalla de cumplimiento:** los datos se muestran por SQL en la demo y la 013 lo lista como pendiente.
2. **9, el E2E de sesión** (`::la_api_no_tiene_dominio_publico`, recargar y storage vacío): quedan los tests de Vitest y el `check_cabeceras` de CI. El E2E de CSP del paso 4 no se corta.
3. **`SESSION_SECRET_ANTERIOR`:** en el evento nadie rota el secret. Se van su test y su chequeo en `verificar_entorno`, y la doc dice que rotar corta las sesiones vivas.
4. **Límites por tenant de `intake/*` y `calificaciones/importar`:** quedan login, `vista-previa` y `ejecutar`, que son los que gastan más.

**Nunca se cortan:** la revisión `security` de 002–008 (paso 1), CodeQL, gitleaks y la lista de required checks con su test, el test de PII transversal con el middleware de errores, el rate limit del login con el semáforo de scrypt, el access fuera del storage, la CSP y la cookie `HttpOnly` con `SameSite=Strict`. La cookie es la única excepción posible: si falla la red privada de Railway, se cae con la degradación escrita en la 013 (ver Riesgos).
