# Auditoría de seguridad — 006 Fase 3, adaptador `sitio_web`

## 2026-10-18 — Fase A (seguridad), cierre de T012/T013

**Alcance:** `backend/app/modulos/enriquecimiento/infraestructura/adaptadores/sitio_web.py` (163 líneas, sin
commitear), `backend/tests/unit/enriquecimiento/test_sitio_web.py` (354 líneas, nuevo) y las notas sumadas a
`specs/006-enriquecedor-contactable/plan.md`. Rama `feature/006-enriquecedor`, worktree
`/Users/danielmendieta/PycharmProjects/h30x-006-impl`. Foco pedido: SSRF por salto, robots.txt, tope de 2 MB,
3 redirecciones, nada del contenido en logs, más inyección de prompt en lo que sale del adaptador.

**Veredicto: RECHAZADO** por un HIGH de disponibilidad (ReDoS en `_MAILTO`, hallazgo 1) y un MEDIUM de
cumplimiento de robots.txt (hallazgo 2). Los dos se corrigen en una línea cada uno, con test rojo primero.
Las cinco defensas del foco de Daniel (SSRF por salto, anti-rebinding, 2 MB decodificados, 3 saltos, logs sin
contenido) están bien implementadas y los sabotajes lo demuestran; el rechazo no es por ellas.

### Resumen

| # | Hallazgo | Archivo:línea | Severidad | Eje |
|---|----------|---------------|-----------|-----|
| 1 | ReDoS: `_MAILTO` es cuadrática sobre la página; 2 MB hostiles ≈ 39 min de CPU por lead | `sitio_web.py:31`, `:155` | **HIGH** | 5 seguridad (A06/A10) |
| 2 | robots.txt se evalúa con el UA completo: una regla `User-agent: EnriquecedorBot` se ignora; una para `Mozilla` se obedece | `sitio_web.py:63`, `:120` | **MEDIUM** | 5 seguridad (cumplimiento `fuentes-publicas`) |
| 3 | Sin plazo total: `timeout=5.0` es por operación de socket; un servidor que gotea bytes retiene al worker sin límite | `sitio_web.py:29`, `:88` | MEDIUM | 5 seguridad / 7 concurrencia (A06) |
| 4 | Emails extraídos sin tope de cantidad ni longitud y sin forma validada: salen del adaptador tal cual los escribió el sitio | `sitio_web.py:31`, `:155` | LOW | 5 seguridad (frontera hacia Fase 4) |
| 5 | robots.txt con 3xx se trata como "sin reglas" (RFC 9309 pide seguir hasta 5 saltos) | `sitio_web.py:113-114` | LOW | 5 seguridad (cumplimiento) |
| 6 | `httpx` loguea a INFO `HTTP Request: GET https://<ip>/<path>` por cada salto; el path lo dicta el sitio | `sitio_web.py:131` (indirecto) | LOW | 5 seguridad (A09) |
| 7 | `is_global` deja pasar `fec0::/10`, `64:ff9b::/96` y `::/96` (IPv4-compatible); sólo explotable con NAT64 o site-local en el host | `sitio_web.py:53` | LOW | 5 seguridad (SSRF residual) |
| 8 | `except ... KeyError` existe para el DNS falso del test; en producción enmascararía un bug como "fallo" | `sitio_web.py:77-78` | LOW | 3 prácticas |

### Hallazgo 1 — HIGH — ReDoS en `_MAILTO` (`sitio_web.py:31`, usada en `:155`)

```python
_MAILTO = re.compile(r"mailto:([^\"'?<>\s]+@[^\"'?<>\s]+)", re.I)
...
emails = tuple(dict.fromkeys(m.lower() for m in _MAILTO.findall(html)))
```

**Modo de falla.** Input: una página de hasta 2 MB sin comillas, espacios ni `@`, con muchas ocurrencias de
`mailto:` (por ejemplo `"mailto:" * 300_000` = 2,1 MB, que el tope de 2 MB deja pasar truncada a 2 MiB). En
cada ocurrencia el motor consume con `[^\"'?<>\s]+` hasta el final de la página y retrocede carácter por
carácter buscando `@`: O(n) por ocurrencia, O(n²) total. Estado: el worker de enriquecimiento está ocupado en
`_extraer` con el GIL tomado. Resultado: el lead bloquea la corrida durante decenas de minutos; el atacante es
cualquier sitio al que apunte un `web_canal` de OSM (dato público, no controlado por zenlo), y lo puede repetir
por cada lead que registre.

**Medido** (`uv run python`, Python 3.12.13, este Mac):

| tamaño | tiempo | relación |
|--------|--------|----------|
| 14 000 B | 0,132 s | — |
| 28 000 B | 0,416 s | ×3,2 |
| 56 000 B | 1,664 s | ×4,0 |
| 112 000 B | 6,680 s | ×4,0 |

×4 por cada ×2 = cuadrático. Extrapolación a 2 MiB: (2 097 152 / 112 000)² × 6,68 s ≈ **2 340 s (39 min)**.
No lo corrí completo a propósito.

**Por qué las guardas existentes no lo atrapan.** El tope de 2 MB (`_leer`, `:149`) limita el input, pero
2 MB cuadráticos ya son 39 min. El `timeout=5.0` (`:88`) es de socket: la página ya se descargó cuando se
ejecuta la regex. `_WA_ME` y `_TELEFONO` no tienen el problema (medido: 2 MB de dígitos en 0,026 s;
181 818 `mailto:a@b ` en 0,025 s).

**Camino de arreglo (para la Fase B, con rojo primero).** Acotar las dos partes y excluir `@` de la parte
local; así cada intento cuesta a lo sumo 64+255 pasos. Medido con
`mailto:([^\"'?<>\s@]{1,64}@[^\"'?<>\s@]{1,255})`: 112 kB en 0,009 s, 2,1 MB en 0,186 s, y sigue extrayendo
`contacto@empresa.co` y `Ventas@Empresa.co?subject=x` → `ventas@empresa.co`. Test rojo sugerido: página
`"mailto:" * 50_000` debe resolverse en < 1 s (con `time.perf_counter`, no reloj de pared de pytest).
Excluir `@` solo, sin acotar, NO alcanza: sigue siendo O(n) por ocurrencia (lo probé: el proceso no terminó en
180 s con 2,1 MB).

### Hallazgo 2 — MEDIUM — robots.txt se consulta con el UA completo (`sitio_web.py:63`, `:120`)

```python
USER_AGENT = "Mozilla/5.0 (compatible; EnriquecedorBot/1.0)"
...
if not reglas.can_fetch(self.USER_AGENT, str(url)):
```

`RobotFileParser.can_fetch` recorta el agente en el primer `/` y baja a minúsculas: compara contra
`"mozilla"`, no contra `"enriquecedorbot"`. **Medido** en el intérprete del proyecto:

| robots.txt | `can_fetch(USER_AGENT)` | `can_fetch("EnriquecedorBot")` |
|-----------|-------------------------|--------------------------------|
| `User-agent: EnriquecedorBot` / `Disallow: /` | **True (crawlea)** | False |
| `User-agent: Mozilla` / `Disallow: /` | False | True |
| `User-agent: *` / `Disallow: /` | False | False |

**Modo de falla.** Un sitio que prohíbe explícitamente a nuestro bot por su nombre (lo que `fuentes-publicas`
y la propia identificación del UA invitan a hacer) es crawleado igual; uno que prohíbe a "Mozilla" (raro, pero
existe) nos bloquea sin motivo. Los tests sólo cubren `User-agent: *` (`test_sitio_web.py:147`, `:263`),
por eso el sabotaje `ua_vacio` sobrevivió: con UA vacío, `can_fetch("")` también cae en `*`.

**Camino de arreglo.** Pasar el product token (`"EnriquecedorBot"`) a `can_fetch`, manteniendo el UA
completo en el header. Rojo: robots con `User-agent: EnriquecedorBot\nDisallow: /` → `fetch_bloqueado_por_robots`.

### Hallazgo 3 — MEDIUM — sin plazo total por fetch (`sitio_web.py:29`, `:88`)

`httpx.Client(timeout=TIMEOUT_S)` reparte 5 s a connect/read/write/pool, cada uno **por operación**. Un
servidor que entrega 1 byte cada 4 s nunca dispara `ReadTimeout`; con el tope de 2 MB el peor caso teórico
son días, y el real (chunked a 1 byte/4 s hasta que el atacante se aburra) es un worker ocupado sin cota. Se
suma a la cadena: hasta 4 saltos × (robots + página) = 8 requests por lead, cada uno sin plazo total. Esto es
la misma familia que el hallazgo 2 (MEDIUM) de `documentos-v2-tarjeta14.md` (sin tope por tanda). Mitigación
mínima: un deadline de reloj monotónico en `_leer`/`obtener` (p. ej. 15 s totales) que levante
`_RespuestaInvalida`. `test_user_agent_fijo_y_timeout_corto` (`:189`) sólo verifica que haya timeout por
operación.

### Hallazgo 4 — LOW — lo que sale del adaptador hacia la Fase 4/5 (`sitio_web.py:31`, `:155`)

Qué sale: `emails: tuple[str, ...]` con cualquier byte salvo `"'?<>` y espacios (sí incluye `\x00`, `\x1b`,
unicode, `{{`, backticks), sin tope de longitud ni de cantidad; `telefonos` son sólo dígitos (seguros).
Según `spec.md:143` el payload de `jev_classify` es `{actividad_declarada, nombre_negocio, ciudad,
descripcion_icp}`: **los emails no llegan al LLM**, así que inyección de prompt por este adaptador no aplica
en la Fase 5 tal como está especificada. Sí llegan al `Cifrador` y a `es_contacto_nominal`
(`dominio/contactable.py:9`, regex anclada y lineal, sin problema). Riesgo residual: una página de 2 MB puede
devolver ~180 000 emails o uno de 2 MB; si la Fase 4 los persiste o los loguea sin filtrar, la bomba la paga
ella. Recomendación para la Fase 4, no para este archivo: quedarse con los primeros N y validar forma
(`^[^@\s]{1,64}@[^@\s]{1,255}$`) antes de cifrar. Si en el futuro un email entra a un prompt, tratarlo como
dato (campo con clave), nunca interpolado en el texto.

### Hallazgo 5 — LOW — robots.txt 3xx = "sin reglas" (`sitio_web.py:113-114`)

RFC 9309 §2.3.1.2: el crawler debe seguir al menos 5 redirecciones de `robots.txt`. Hoy un `301` en
`/robots.txt` se trata como ausencia de reglas y se pide la página. En la práctica el caso típico
(`empresa.co` → `www.empresa.co`) queda cubierto porque la página también redirige y el `www` tiene su propio
robots (`test_redireccion_a_www_se_sigue_con_su_robots`); el agujero es un sitio cuyo robots redirige y cuya
página no. Decisión 5 del coordinador (5xx bloquea, 4xx permite, mismo tope de 2 MB): correcta, RFC 9309
§2.3.1.3/§2.3.1.4; el tope de 2 MB supera los 500 KiB mínimos del RFC.

### Hallazgo 6 — LOW — `httpx` loguea cada salto a INFO (indirecto, `sitio_web.py:131`)

`httpx._client` emite `logger.info('HTTP Request: GET https://<ip>/<path> "HTTP/1.1 200 OK"')` por cada
`send`; `observability.py:130` pone el root en `LOG_LEVEL` (INFO por defecto en `docker-compose.yml:107`).
Por lo tanto en producción sale una línea por request con la IP del sitio y el path (que el sitio elige vía
`Location`). No es contenido de la página ni dato de un lead; el test `test_log_no_contiene_el_contacto_extraido`
corre a DEBUG y pasa, así que el cuerpo no se loguea. Queda como ruido y como canal de un tercero hacia los
logs (un `Location: /?x=<lo que quiera>`). Si molesta: `logging.getLogger("httpx").setLevel(logging.WARNING)`
en `observability.py`, no acá.

### Hallazgo 7 — LOW — residuos de `is_global` (`sitio_web.py:53`)

Medido en Python 3.12.13: `fec0::1` (site-local, deprecado) → `is_global=True`; `64:ff9b::7f00:1` (NAT64
hacia 127.0.0.1) → `True`; `::7f00:1` (IPv4-compatible, deprecado) → `True`. Los tres sólo llegan a algo
interno si el host tiene una ruta site-local o un gateway NAT64, y el gateway traduce al loopback del
gateway, no al nuestro. No es explotable en un contenedor Railway estándar; lo dejo registrado para cuando
cambie la red. Los mapeados (`::ffff:127.0.0.1`, `::ffff:10.0.0.1`), 6to4 (`2002:7f00:1::`), `0.0.0.0`,
`100.64/10`, `192.0.0.0/24`, `198.18/15`, `240/4`, `224.0.0.1`, `ff02::1` y `::` se rechazan (medido).

### Hallazgo 8 — LOW — `KeyError` en el `except` (`sitio_web.py:77-78`)

Está para el `Dns` del test (`test_sitio_web.py:41`, `self.tabla[host]`). En producción el resolver real
va a lanzar `socket.gaierror` (ya cubierto por `OSError`); atrapar `KeyError` además convierte en `"fallo"`
silencioso cualquier bug de diccionario en `_extraer`/`_leer`. Alternativa: que el `Dns` falso devuelva `[]`
para hosts desconocidos y sacar `KeyError`.

### Juicio sobre las seis decisiones de diseño

1. **Anti-rebinding: resolver una vez por salto, conectar a la IP con `Host` y `sni_hostname`.** Correcto.
   `httpcore 1.0.9` `_sync/connection.py:107,151` pasa `sni_hostname` como `server_hostname` al `ssl` →
   el certificado se verifica contra el nombre real, con `verify=True` por defecto. `Host` explícito se
   respeta (httpx sólo lo autogenera si falta; `test_conecta_a_la_ip_validada_con_el_host_original`). La IP
   del salto sirve para robots y página: bien, es la misma ventana. IPv6 literal queda bracketeado por
   `copy_with(host=)` (medido: `https://[2606:4700::1]/`). `trust_env=False` evita proxies del entorno.
   Un `Location` con userinfo (`https://x@empresa.co/`) o puerto (`:6379`) pasa el chequeo de host; httpx
   mandaría Basic auth con esas credenciales y conectaría a ese puerto, pero siempre a la IP pública validada
   del propio sitio: inocuo.
2. **`is_global` + `is_multicast` sin unwrap de ipv4_mapped.** Correcto en el rango que fija el proyecto.
   `pyproject.toml:4` `>=3.12,<3.13`, `Dockerfile:2,9` `python:3.12.15-slim`, local 3.12.13. El cambio de
   gh-113171 (CVE-2024-4032) entró en 3.12.4; en 3.12.0–3.12.3 `::ffff:0:0/96` entero era `is_private`, así
   que los mapeados privados también se rechazaban (sobre-bloqueando los públicos mapeados, que es el lado
   seguro). El test parametrizado con `::ffff:127.0.0.1` y `::ffff:10.0.0.1` (`:56`) lo fija en cualquier
   3.12. Que el sabotaje `sin_unwrap_ipv4_mapped` sobreviva es esperable: la guarda era redundante y se quitó,
   como pide `verificar-antes-de-afirmar` §9. Recomiendo subir `.python-version` a `3.12.15` para que el
   venv local no pueda caer en un 3.12 viejo; no es bloqueante.
3. **Iterar `respuesta.stream` en vez de `iter_raw()`.** No cambia el tope ni el cierre. Con transporte real
   `stream` es `BoundSyncStream` sobre el stream de httpcore y entrega bytes crudos por chunk (≤ 64 KiB); el
   `finally: respuesta.close()` (`:105`, `:117`) cierra el stream de httpcore y, al no estar consumido, la
   conexión se descarta en vez de volver al pool. Lo único que se pierde es la contabilidad
   `num_bytes_downloaded`/`is_stream_consumed`, que nadie usa. **Medido** el lazo de descompresión: gzip con
   basura al final, dos miembros, zlib-deflate, exactamente 2 MiB (no truncado), 2 MiB + 1 (truncado), vacío
   y gzip cortado a 30 bytes, todos terminan sin lanzar; raw deflate lanza `zlib.error` → `fallo` (aceptable,
   es un servidor roto).
4. **Cross-host: igualdad exacta tras quitar `www.`.** Correcto y estricto. httpx normaliza el host a
   minúsculas (medido: `WWW.Empresa.CO` → `www.empresa.co`), `https://evil.com@empresa.co/` resuelve a
   `empresa.co` y `https://empresa.co\@evil.com/` a `evil.com` (bloqueado). El sabotaje `endswith_sin_punto`
   murió con `notempresa.co`. Un subdominio (`m.empresa.co`) corta con `fallo`: limitación funcional
   documentada en `plan.md`, no de seguridad.
5. **robots 5xx bloquea, 4xx permite, mismo tope.** Correcto (ver hallazgo 5 para el 3xx).
6. **Log `motivo=type(e).__name__` + lead_id.** Correcto. Que `motivo_con_mensaje` sobreviva es esperable:
   ninguna excepción del `except` lleva contenido (`IPPrivadaRechazada(host)` lleva el host, que ya está en
   el lead; `DemasiadasRedirecciones(url)` lleva la URL inicial). Igual, el nombre del tipo basta y es lo que
   hay que mantener: si mañana alguien agrega `str(e)`, `httpx.HTTPStatusError` sí lleva la URL del salto.
   Para que un test lo fije, haría falta un fallo cuyo mensaje contenga un dato del sitio: un `Location`
   inválido con un email adentro (`InvalidURL` lleva la URL) serviría como rojo.

### OWASP Top 10 2025, categoría por categoría

| Cat. | Veredicto | Evidencia |
|------|-----------|-----------|
| A01 Broken Access Control | Sin hallazgo | El adaptador no toca base ni tenant; recibe `lead_id` y lo pasa a `RegistroCostos` (`:124-126`). El scope lo pone el caso de uso de la Fase 4. |
| A02 Security Misconfiguration | Sin hallazgo | `trust_env=False` (`:88`), `verify` por defecto, `Accept-Encoding: identity` (`:129`), UA fijo sin "zenlo" (`test:187`). |
| A03 Software Supply Chain | No verificado hoy | Sin red por instrucción del coordinador. Stack del adaptador: httpx 0.28.1, httpcore 1.0.9, h11 0.16.0, idna 3.20, certifi 2026.7.22. La última consulta OSV registrada (`documentos-v2-tarjeta14.md`, 2026-10-07, 86 paquetes) dio 0 avisos; no hubo cambios de dependencias en este diff (`git status`: sólo `sitio_web.py`, el test y specs). |
| A04 Cryptographic Failures | Sin hallazgo | TLS con verificación de certificado contra el host real vía `sni_hostname` (decisión 1). El contacto extraído viaja en memoria hasta el `Cifrador` de la Fase 4 (`puertos.py:11`). |
| A05 Injection | Sin hallazgo | Sin SQL ni shell. Los emails salen crudos (hallazgo 4, LOW) pero no entran a ningún prompt según `spec.md:143`. |
| A06 Insecure Design | **Hallazgo 1 (HIGH), 3 (MEDIUM)** | Regex cuadrática sobre input hostil; sin plazo total por fetch. |
| A07 Authentication Failures | Sin hallazgo | No aplica. |
| A08 Software or Data Integrity | Sin hallazgo | Costo registrado antes de cada request real (`:124`), incluido robots; SSRF cortado no registra (P9, `test:91`). |
| A09 Logging & Alerting | **Hallazgo 6 (LOW)** | Línea INFO de httpx por salto con IP y path del sitio. El log propio no lleva contenido (`:79`, `test:344-354` a DEBUG). |
| A10 Mishandling of Exceptional Conditions | **Hallazgo 8 (LOW)** | `KeyError` atrapado de más. El resto del `except` (`:77-78`) es la lista correcta; nada se traga silenciosamente fuera de ella. |

### SSRF por salto, verificado línea por línea

- `obtener` (`:89-106`): el bucle corre `MAX_REDIRECCIONES + 1 = 4` veces; en cada vuelta y **antes** de
  cualquier request: esquema ∈ {http, https} y host no vacío (`:90`), host del lead (`:90`),
  `validar_destino` (`:92`), robots por host (`:93-95`). Sabotajes `solo_url_inicial`, `any_por_all`,
  `sin_guarda_esquema`, `sin_guarda_cross_host`, `mayor_3_por_4`, `conectar_por_nombre` murieron.
- `validar_destino` (`:44-55`): rechaza resolución vacía, IP no parseable, y exige que **todas** las IPs
  sean globales y no multicast; devuelve `ips[0]`. Correcto.
- Costo: `_pedir` registra antes de `send` (`:124`), por lo que un `ConnectTimeout` también cuenta como
  request real. Coherente con P9 ("request real" = intento), lo anoto por si Daniel lo entiende distinto.

### Tests (eje 4)

44 tests, verdes en 0,50 s sin red. Rojo verificado: `rojo_f3_v2.txt` (40 fallos por `DID NOT RAISE` /
`AssertionError` sobre resultados, no `ImportError`) y `rojo_f3_v3.txt` (los 4 sumados fallan por assert
sobre `estado`/UA). 27 sabotajes en `sabotajes_f3.txt`: 24 muertos, 3 sobreviven con explicación
(`sin_unwrap_ipv4_mapped` y `motivo_con_mensaje`, justificados arriba; `ua_vacio` apunta al hallazgo 2).
Los `for` con asserts (`test:185-189`, `:336-341`) están guardados por `assert red.requests` y
`len(...) == 3`. Ningún test lee el reloj de pared. Faltan (para la Fase B): robots con el token del bot,
ReDoS, plazo total.

### Concurrencia (eje 7)

Sin estado compartido: `httpx.Client` y `RobotFileParser` se crean por llamada, `robots_ok` es local. Dos
workers sobre el mismo lead hacen dos fetches y dos filas de costo: la idempotencia, si hace falta, es del
caso de uso de la Fase 4, no del adaptador.

### Medido

- `uv run pytest -q tests/unit/enriquecimiento/test_sitio_web.py` → `44 passed in 0.50s`.
- Python: `uv run python -c "import sys; print(sys.version)"` → 3.12.13; `Dockerfile` 3.12.15;
  `pyproject.toml` `>=3.12,<3.13`; `.python-version` `3.12`.
- `is_global`/`is_multicast` sobre 17 direcciones (tabla en hallazgo 7).
- `RobotFileParser.can_fetch` con tres robots (tabla en hallazgo 2).
- `_MAILTO.findall` sobre `"mailto:" * n` para n ∈ {2000, 4000, 8000, 16000} (tabla en hallazgo 1) y
  regex acotada sobre 112 kB y 2,1 MB.
- `_leer` sobre 8 cuerpos (decisión 3).
- `httpx.URL.join` con host en mayúsculas, userinfo, backslash y puerto (decisión 4).
- `httpcore/_sync/connection.py:107,151` (`sni_hostname` → `server_hostname`).
- `httpx/_client.py`: `logger.info('HTTP Request: ...')` (hallazgo 6); `observability.py:130` root a
  `LOG_LEVEL`; `docker-compose.yml:107` `INFO` por defecto.

### No verificado

- **OSV / `npm audit` / portada de OWASP**: no consultados hoy porque el coordinador pidió "no uses red
  real". La tabla A03 cita la consulta del 2026-10-07; `/private/tmp/claude-501/osv/` está vacío, así que
  no pude re-leer los archivos de aquella vez. Antes de mergear la 006 corresponde repetir la consulta.
- **Latencia (eje 6)**: sin endpoint ni datos en Tempo; nada que medir.
- **Comportamiento con transporte real** (chunks de httpcore, cierre de conexión a medio stream): inferido
  del código fuente de httpx/httpcore instalados, no ejecutado contra un servidor.
- **Red del host de despliegue** (NAT64, site-local) para el hallazgo 7.

## 2026-10-18 — Re-revisión tras los arreglos (T012, cierre)

**Alcance:** mismo archivo (`sitio_web.py`, ahora 185 líneas) y tests (`test_sitio_web.py`, 434 líneas), sin
commitear en `feature/006-enriquecedor`. Verificado en disco, no por el informe del lead: `git diff --stat`
muestra sólo `sitio_web.py`, `plan.md` y `tasks.md`; el test sigue `??`.

**Veredicto: APROBADO.** El HIGH y los dos MEDIUM están corregidos con test que los fija. Quedan abiertos los
LOW 5, 6, 7 y 8 (sin cambio), el LOW 4 mitigado a medias, y un LOW nuevo (9) sobre el plazo efectivo. Ninguno
bloquea el merge; van a la lista de deuda del módulo.

### Estado de cada hallazgo

| # | Hallazgo | Estado | Evidencia |
|---|----------|--------|-----------|
| 1 | ReDoS en `_MAILTO` | **Cerrado** | `sitio_web.py:33`: `mailto:([^\"'?<>\s@]{1,64}@[^\"'?<>\s@]{1,255})`. Medido: 2 097 152 B de `mailto:` repetido → 0,156 s (antes extrapolaba 39 min); `_extraer` completo sobre ese cuerpo 0,250 s; 1,64 MB de `mailto:` + 65 letras 0,020 s; `mailto:` + 2 MB de `x` 0,011 s. Sigue extrayendo `Ventas@Empresa.co?subject=x` → `ventas@empresa.co`. Test `test_mailto_sin_arroba_no_es_cuadratico` (`:372`, `perf_counter`, no reloj de pared). |
| 2 | robots con UA completo | **Cerrado** | `sitio_web.py:74` `TOKEN_ROBOTS = "EnriquecedorBot"`, usado en `:140`; el UA del header sigue siendo el completo (`:147`). Medido: `can_fetch("EnriquecedorBot")` → False y con el UA completo → True sobre `User-agent: EnriquecedorBot / Disallow: /`. Test `:383`. |
| 3 | Sin plazo total | **Cerrado** (ver 9) | `PLAZO_TOTAL_S = 20.0` (`:31`), reloj inyectable (`:77`, default `time.monotonic`), `limite` por `obtener` (`:100`), chequeo al inicio de cada salto (`:107`) y por cada chunk crudo en `_leer` (`:163`), que también usa robots (`:135`). `_PlazoVencido` → `fallo` (`:89`). Tests `:394` (goteo: ≤ 10 chunks) y `:413` (headers lentos: corta antes de `/r2`, 3 filas de costo). |
| 4 | Emails sin tope ni forma | **Mitigado, abierto** | La regex nueva acota la longitud (≤ 320 chars) y prohíbe `@` en cada parte. Sigue sin tope de cantidad (`:177`): 2 MiB de `mailto:a@b ` son ~180 000 emails. La recomendación para la Fase 4 (quedarse con los primeros N) sigue en pie. |
| 5 | robots 3xx = sin reglas | **Abierto** | `:133-134` sin cambio. |
| 6 | `httpx` loguea INFO por salto | **Abierto** | Fuera de este archivo (`observability.py`). |
| 7 | residuos de `is_global` | **Abierto** | `:59` sin cambio; sigue siendo no explotable en la red actual. |
| 8 | `KeyError` en el `except` | **Abierto** | `:90` sin cambio. |
| 9 | **Nuevo, LOW**: el plazo nominal es 20 s pero el efectivo en el peor caso ronda los 60 s | Abierto | Ver abajo. |

### Hallazgo 9 — LOW — plazo efectivo ≈ 3× el nominal (`sitio_web.py:107`, `:113-115`)

`chequear_plazo()` corre al inicio del salto y después de cada chunk, pero no entre el robots y la página del
mismo salto. Secuencia peor: el chequeo de `:107` pasa en t = 19,9 s; robots (`:113`) gasta connect 5 +
write 5 + headers 5 + primer chunk 5 = 20 s hasta el primer chequeo de `_leer`, que corta... salvo que robots
devuelva 404 sin cuerpo (`:133-134` retorna antes de `_leer`), y entonces la página (`:115`) arranca en
t ≈ 35 s con otros 20 s hasta su primer chequeo. Resultado: hasta ~55-60 s por lead, acotado y sin bucle,
por eso LOW. Un `chequear_plazo()` dentro de `_pedir` (antes de `send`, `:152`) lo deja en ≈ 40 s y hace
innecesario el de `:107`. No fabricar un test con reloj de pared: el de `:413` sirve de molde.

### Foco del cierre, verificado línea por línea

- **SSRF por cada salto.** Bucle de 4 vueltas (`:106`); en cada una, antes de cualquier request: esquema y
  host (`:109`), mismo dominio sin `www.` (`:109`), `validar_destino` (`:111`), robots por host (`:112-114`).
  `httpx.Client().follow_redirects` es `False` (medido), así que ningún salto lo sigue httpx por su cuenta.
  Conexión a la IP validada con `Host` y `sni_hostname` (`:145-148`), ahora con el host en punycode
  (`_host`, `:64-65`): medido `httpx.URL("https://café.co/").raw_host == b"xn--caf-dma.co"`, también en
  mayúsculas y vía `join`; un host IDNA inválido lanza `httpx.InvalidURL`, que está en el `except` (`:89`).
  Test `:346` fija punycode en Host y una fila de costo por request. Sin cambio en `validar_destino`
  (`:50-61`); los 12 casos privados/mapeados/multicast del parametrizado (`:56`) siguen verdes.
- **robots.txt.** Por host, con token del producto (`:140`), 5xx bloquea (`:131`), 4xx permite (`:133`),
  cuerpo con el mismo tope y el mismo plazo (`:135`). Un robots de 2 MB se trunca y se parsea lo leído:
  conservador (sin la parte perdida, `can_fetch` tiende a permitir); RFC 9309 admite el truncado a 500 KiB.
- **Tope de 2 MB.** `_leer` (`:155-173`) sin cambio salvo el chequeo de plazo: `max_length` en el
  descompresor (`:166`), corte sobre bytes decodificados (`:171`), `close()` en `finally` (`:124`, `:137`).
- **3 redirecciones.** `range(MAX_REDIRECCIONES + 1)` (`:106`) + `DemasiadasRedirecciones` (`:125`); test
  `:202` sigue contando 4 requests, no 5.
- **Nada del contenido en logs.** Único log propio: `:91`, `lead_id` + `type(e).__name__`. `_PlazoVencido`,
  `_RespuestaInvalida` y `_BloqueadoPorRobots` se lanzan sin mensaje. Test `:357` a DEBUG sigue verde.
- **Costo después de `build_request`** (`:149`): si el pedido no se arma, no hay fila; si se arma y falla en
  `send`, hay fila (request real = intento, igual que en la revisión anterior).

### Sabotajes declarados por el lead

No los ejecuté (no se toca código en esta fase); verifiqué por lectura que cada uno tiene un test que lo
mata: `regex_mailto_sin_tope` → `:372` (0,5 s contra ~7 s medidos); `robots_con_user_agent` → `:383`;
`sin_plazo_en_lectura` → `:394` (sin chequeo por chunk el goteo llega a 2 MB y devuelve `truncado`, no
`fallo`); `plazo_que_nunca_vence` → `:394` y `:413`; `sin_plazo_por_salto` → `:413` (aparecería
`empresa.co/r2` en `paths()`).

### Medido

- `cd backend && uv run pytest -q tests/unit/enriquecimiento/` → `57 passed in 0.56s`, sin red.
- `_MAILTO.findall` sobre cuatro cuerpos hostiles de hasta 2 MiB (tabla en hallazgo 1); `_extraer` completo.
- `httpx.URL(...).raw_host` sobre `café.co`, `CAFÉ.co`, `xn--caf-dma.co`, `[2606:4700::1]`, `empresa.co.` y
  un IDNA inválido; `httpx.URL.join` con host en mayúsculas.
- `RobotFileParser.can_fetch` con token y con UA completo.
- `httpx.Client().follow_redirects` → `False`. Python 3.12.13.

### No verificado

- OSV / `npm audit` / portada OWASP: sin red por instrucción del coordinador, igual que en la revisión
  anterior. Sin cambios de dependencias en el diff. Repetir antes del merge de la 006.
- Sabotajes: por lectura, no por ejecución (ver arriba).
- Transporte real (chunks de httpcore, timeouts de socket reales): inferido del código, no ejecutado.
