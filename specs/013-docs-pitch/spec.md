# Spec 013 — Docs y pitch: README de operación, arquitectura consolidada y guion para el jurado

**Slice:** 013 · **Rama:** `feature/013-docs-pitch` · **Tiempo:** domingo PM (PRD §9, item 13: "README + arquitectura + video de respaldo (Cap) + pitch")
**Depende de:** 002–012 ya especificadas y, para los pendientes que lista, cerradas — cada "Fuera del alcance" que una spec anterior derivó a esta spec necesita existir primero para poder citarlo con evidencia. **Desbloquea:** nada. Es el cierre.

> Esta spec no agrega producto ni toca código. Junta lo que las demás ya construyeron y lo deja legible para quien no escribió una línea: el jurado, un mentor, Dapta, o el propio equipo en seis meses. No hay puerto nuevo, no hay test de pytest o Vitest que nazca en rojo — el "Terminado cuando" de esta spec son documentos verificables por contenido y un guion cronometrado, no código que corra en CI.

## Para quién
- **El jurado del 30X:** entiende en 5 minutos qué mide el tablero y por qué importa, con la rúbrica del PRD §10 ya resuelta en el guion, sin tener que leer código.
- **Dapta:** lee en `docs/arquitectura-backend.md` y `docs/arquitectura-frontend.md` cómo entra un lead, qué pasa con sus datos y dónde se corta hoy la integración (`dapta_csv` primero, `dapta_api` si llega la doc).
- **El equipo, después del evento:** tiene un README que de verdad levanta el stack y hace el deploy, sin adivinar comandos.

## Qué hace
1. **README de operación** (raíz del repo, ya existe: lo completa, no lo reemplaza). Pone al día "Estado" (hoy solo lista 001 y 002 como "pendiente", desactualizado desde el merge de main), completa "Correr local" con los comandos reales de `CLAUDE.md`, suma "Deploy" (Railway: 2 servicios; Supabase: pooler en modo transacción para `api`, modo sesión para migraciones) y "Verificar protección de rama y cumplimiento" (`verificar_proteccion.sh` y la consulta/pantalla de cumplimiento de la 012).
2. **`docs/arquitectura-backend.md` y `docs/arquitectura-frontend.md` consolidados.** En `main` todavía no existen (solo `docs/decisiones.md`, `docs/flujo.html` y `docs/prd.md`), pero cada slice escribe su parte en su propio PR: 002, 003, 004, 005, 006, 007, 008, 009, 010, 011 y 012, en el paso de doc de cada plan. La 013 no los crea desde cero ni pisa lo escrito: los consolida (orden, duplicados, huecos) en hexagonal, puertos/adaptadores en `backend/config/fuentes.yaml`, dominio, costos, cumplimiento y sesión, y completa las secciones que algún slice recortó ("lo primero que se recorta", 002/003/004/011).
3. **Guion de 5 minutos para el pitch**, con la estructura del PRD §10 (Problema → Solución en acción → Impacto → Qué se necesita para implementarlo) y el embudo real del tablero: `encontrados → únicos → icp → contactables → contactados → respondieron → calificados` (columnas reales de `v_tablero_fuentes`, construidas por 005, 006, 007 y 008, en ese orden), con CPL y CPQL por fuente y canal.
4. **Lista "qué es real y qué es simulado"** para el jurado (lo que la 003 deriva, atribución OSM y deuda de doc, va al README y a la arquitectura, no a esta lista): un ítem por cada pendiente que 005, 007, 008, 009, 010, 011 y 012 derivaron explícitamente a esta spec (dos de ellas, 011 y 012, lo dicen en esas palabras: "la 013 lo lista" / "la 013 los lista... no se esconden"), más el gasto de CI reportado aparte del CPL y el CPQL, que la propia 012 ya exige ("la 013 reporta el gasto de CI... leído de la consola de la cuenta del evento").

## Puertos y adaptadores que toca (`backend/config/fuentes.yaml`)
Ninguno. Es documentación: no agrega, quita ni habilita/deshabilita un adaptador, y no toca el archivo de config.

## Skills que aplican
Ninguna skill de dominio (no hay fuente, canal ni operación de costo nueva que verificar). Antes de cerrar esta spec corre la skill `que-falta` (`CLAUDE.md`): es exactamente la pregunta que esta spec le contesta al jurado, así que no se cierra sin pasarla primero sobre el propio contenido.

## Evals
Ninguno. No hay salida de LLM que puntuar: es prosa escrita por un humano a partir de las specs ya cerradas, revisada por el agente `advisor`.

## Flujo principal
1. Confirmar contra las specs (002–012) la lista cruda de pendientes derivados: "Fuera del alcance" de 005, 007, 008, 009, 010, 011 y 012, más cada línea de `grep -n '013' specs/0*/spec.md` (incluye 003: atribución OSM y deuda de doc). Sin inventar ninguno nuevo.
2. Escribir `docs/arquitectura-backend.md` y `docs/arquitectura-frontend.md` primero: son la fuente de verdad técnica que el README y el guion van a citar.
3. Completar el README de operación con comandos copiados de `CLAUDE.md` y de los workflows de CI, no inventados.
4. Escribir el guion de pitch usando las columnas reales de `v_tablero_fuentes` y la rúbrica del PRD §10.
5. Escribir la lista "qué es real y qué es simulado": un ítem por pendiente, citando la spec que lo derivó.
6. Una vuelta del agente `advisor` sobre los 4 documentos, aplicar sus correcciones.

## Terminado cuando (verificable sin levantar el stack)

### `README.md` (raíz)
- [ ] "Estado" refleja 010, 011 y 012 como lo que son hoy (especificadas / pendientes de implementar, no "pendiente" a secas heredado de antes del merge). Verificación: `grep -n "pendiente" README.md` ya no cuelga de una tabla desactualizada.
- [ ] "Correr local" tiene los comandos reales de back (`cd backend && uv sync && uv run pytest -q`) y front (`cd frontend && npm ci && npm test && npx playwright test`), copiados de `CLAUDE.md` — no hay un comando en el README que no esté también ahí.
- [ ] Una sección "Deploy" con los pasos a Railway (servicios `api` y `web`) y Supabase (pooler en modo transacción para `api`, modo sesión para migraciones), consistente con `CLAUDE.md` y la constitución (principio V: secrets en Railway/GitHub Environment).
- [ ] Una sección "Verificar protección de rama y cumplimiento" que referencia `verificar_proteccion.sh` (012, paso 2 de su plan) y cómo ver la pantalla o la consulta SQL de cumplimiento (012, "Pantalla de cumplimiento").
- [ ] Atribución de fuentes (cumplimiento de licencia, no estilo): "© OpenStreetMap contributors" con enlace a `https://www.openstreetmap.org/copyright` (ODbL, 003 "Cumplimiento de un lead OSM") y la atribución de datos.gov.co con su licencia (011, "Desbloquea"). Va en la sección "Fuentes y licencias" que el README ya tiene.
- [ ] Si la 008 cortó su eval (008, corte 3), el README dice textualmente "match_dapta: sin medir".
- Verificación de cierre: cada comando y cada script nombrado existe tal cual en `CLAUDE.md` o en la spec citada — se cruza con grep, no se copia de memoria.

### `docs/arquitectura-backend.md`
- [ ] Hexagonal: dominio, puertos, adaptadores, referencia a `backend/config/fuentes.yaml` y a la suite de contrato (constitución, principio I).
- [ ] Dominio: entidades centrales (`leads`, `lead_fuentes`, `costos`, `cumplimiento`, `sesiones_refresco`).
- [ ] Costos: libro de costos, fórmulas de CPL y CPQL citadas del PRD §4 y de 005/008.
- [ ] Cumplimiento: reglas (solo personas jurídicas, solo canales publicados, opt-out) y en qué capa vive cada chequeo.
- [ ] Sesión y seguridad (012): access en memoria, refresh opaco en cookie, rate limiting, cabeceras, proxy same-origin. Si la red privada de Railway falló (012, Riesgos): la degradación escrita: dominio público de la api con `VITE_API_URL`, sin cookie de refresh, el access de 15 min en memoria y recargar pide login. Si no falló, una línea que diga que no hizo falta.
- Verificación de cierre: el archivo existe y cubre las 5 secciones de arriba, cada una con al menos una referencia a la spec de origen. Lo que ya escribieron los slices se conserva (se reordena o se deduplica, no se borra sin motivo).

### `docs/arquitectura-frontend.md`
- [ ] Estructura del front (componentes, organización de carpetas tal como quedó implementada).
- [ ] Cliente API: relativo a `/api` (012), sin tokens en `localStorage`/`sessionStorage` (012).
- [ ] Cómo se arma el tablero: de qué endpoint sale cada columna que ve el jurado (`GET /tablero/fuentes`, 005).
- [ ] Idiomas: la UI en es y en, y la API devuelve códigos, no texto (`CLAUDE.md`, "Idiomas es/en"). Si alguna pantalla quedó solo en español, va a la lista "qué es real y qué es simulado".
- [ ] Pantalla de `whatsapp_meta` (009, corte 4: "la doc pasa a la 013"): si meta se prendió, su pantalla documentada; si no, una línea que diga que no aplica porque `whatsapp_meta` quedó en `habilitado: false`.
- Verificación de cierre: el archivo existe y cubre las 5 secciones de arriba. Lo que ya escribieron los slices se conserva.

### Guion de pitch (`docs/pitch.md`)
- [ ] Sigue la estructura del PRD §10 (Problema → Solución en acción → Impacto → Qué se necesita para implementarlo), con minutos anotados por sección, total ≤ 5 min.
- [ ] El embudo usa las columnas reales de `v_tablero_fuentes`: `encontrados → únicos → icp → contactables → contactados → respondieron → calificados` — no una versión inventada ni reordenada.
- [ ] La secuencia de toques "email → whatsapp (opt-in)" aparece como segundo toque en "Solución en acción" (009, "Desbloquea").
- [ ] CPL y CPQL por fuente y canal, con números reales si ya corrió una búsqueda real al momento de escribir, o los del fixture de 005/008 marcados explícitamente como ejemplo.
- [ ] El gasto de CI (job `revision-seguridad` + evals) aparece reportado aparte del CPL y el CPQL, con el número leído de la consola de la cuenta del evento (exigencia de 012) o "no disponible aún" si todavía no corrió.
- Verificación de cierre: leerlo en voz alta cronometrado una vez. Si pasa de 5 minutos, se recorta antes del pitch real, no durante.

### Lista "qué es real y qué es simulado" (dentro de `docs/pitch.md` o como anexo del mismo archivo)
- [ ] Un ítem por cada pendiente derivado explícitamente, citando la spec de origen:
  - **005:** paginación más allá de la primera página de Croma/Overpass, alta de usuarios por UI/roles/multi-usuario, monedas ≠ USD, ejecución en background con polling, idiomas (portugués, traducir API/docs). Y por su orden de corte, si se cortó: la cola de revisión de dedup (se resuelve por SQL), palabras clave y exclusiones en el formulario (pasan a la 010), `v_costo_por_canal` (pasa a la 007). El E2E y la cobertura por país van en el bloque de la 012, abajo.
  - **007:** WhatsApp y llamada delegados (→009/→008), solo IMAP con polling cada 60 s (sin webhook del proveedor), sin multi-toque, respuesta automática la hace un humano, retención documentada sin job implementado, sin HTML/tracking, costo del tiempo humano de aprobación no registrado, enriquecimiento fuera de `costo_por_respuesta`, `pt` fuera de plantilla de idioma, leads `whatsapp_osm` y `desconocido` no entran (reduce el volumen de OSM).
  - **008:** `dapta_api` OFF hasta la doc `[MENTORES]` (se usa `dapta_csv`), sin reintento a `no_contesta`, `minutos_humanos` no medido este fin de semana, sin re-tarifar filas si cambia la tarifa provisional, sin re-exportar CSV perdido, llamadas las hace Dapta, sin recall de `match_dapta`.
  - **009:** WhatsApp nunca es primer toque (opt-in obligatorio), no se lee ni automatiza el WhatsApp de la pyme, sin envío automático desde el asistido, solo el número publicado (no uno que el lead pase después), sin conversación libre en la ventana de 24 h, sin redacción con LLM para `whatsapp_meta`, un BAJA por WhatsApp da de baja en todos los canales (`[VALIDAR]` si el dueño quiere baja por canal), sin reintento automático ni reapertura del freno, un número por tenant, solo texto sin medios/botones, opt-in solo por respuesta (sin formulario ni QR), sin rate limit propio del webhook (decisión de 012: HMAC + tope de body).
  - **010:** Puerta C ya existía y no se tocó, sin dedup propio en las puertas, no excluye del resultado a empresas ya pegadas en Puerta A, sin autocompletado en vivo, Puerta B de un solo turno, la frase solo en español, fixture sintético de ~10 nombres si no llegó el fixture real `[MENTORES]` de 50, `frase_a_icp` sigue en k=3 (no se bajó a k=1).
  - **011:** sin contacto propio (queda `sin_canal_publicado` hasta fusión con OSM), no guarda personas naturales, una sola página de 5.000 sin paginación, solo Colombia, `ingresos_min` no disponible, el E2E de búsqueda que la 005 cortó.
  - **Lo que la 012 recibió y no es seguridad** (012, primer ítem de "Fuera del alcance"), si se cortó: el E2E de búsqueda (005 corte 2, 011), la cobertura por país y las revisiones pendientes del tablero (005 corte 5), los evals de 007, 008 y 009 (`match_dapta` incluido) y la rama `meta` de la 009.
  - **012, por su propio orden de corte:** pantalla de cumplimiento (si se cortó, los datos se muestran por SQL en la demo), la cookie de refresh si falló la red privada de Railway (012, Riesgos: recargar pide login), E2E de sesión, rotación de `SESSION_SECRET_ANTERIOR`, límites por tenant de `intake/*`/`calificaciones/importar`; más lo que 012 nunca intentó: retención/purga sin job, rate limit por IP (no se puede validar tras Railway/Caddy), rate limit del webhook de WhatsApp y de `/auth/refrescar`, MFA/recuperación de clave/alta de usuarios, WAF/DDoS (lo que dé Railway).
- [ ] El gasto de CI aparece también acá, no solo en el guion — es la misma cifra, citada una vez y referenciada la otra.
- Verificación de cierre, en las dos direcciones:
  - **Sin invención:** cada ítem cita la spec y la sección que lo derivó. No se agrega ningún pendiente que ninguna spec haya mencionado.
  - **Sin omisión:** se recorre cada bullet de "Fuera del alcance" de 005, 007, 008, 009, 010, 011 y 012, y además cada línea de `grep -n '013' specs/0*/spec.md` fuera de esta spec (órdenes de corte, Riesgos, Desbloquea: hoy 003, 005, 007, 008, 009, 011 y 012). Cada una tiene su ítem en esta spec, en la lista, el README, la arquitectura o el guion, o un motivo anotado de por qué no aplica.
  - Para cada ítem condicional ("si se cortó"), la lista dice si se cortó o no al momento del pitch. No queda en condicional.

## Fuera del alcance
- El video de respaldo (Cap): el PRD lo pide en el mismo punto 13, pero es una grabación, no una spec — se hace al final, sin tareas propias acá.
- Cualquier cambio a `backend/`, `frontend/`, migraciones o `backend/config/fuentes.yaml`.
- Reescribir las specs 002–011 para corregir `config/fuentes.yaml` → `backend/config/fuentes.yaml` en su propio texto: ya están cerradas y mergeadas, y `CLAUDE.md` ya tiene la ruta correcta (commit `952738f`). Esta spec usa la ruta correcta solo en sus documentos nuevos.
- Correr una búsqueda real para tener números frescos de CPL/CPQL: usa los que ya existan al momento de escribir, o los del fixture, marcados como tal.
- Resolver cualquiera de los pendientes que lista: esta spec los documenta, no los cierra.

## Decisiones técnicas
- No se crea una skill nueva para esto: el criterio de cierre es la skill `que-falta` ya existente en `CLAUDE.md`.
- Un documento por entregable: el guion de pitch va en `docs/pitch.md` (nuevo), separado del README, porque tiene una audiencia y un tiempo de lectura distintos.
- El "Terminado cuando" de esta spec no tiene pytest/Vitest porque no hay código de producto que probar: quien valida contenido y cobertura es el `advisor`, sobre los 4 documentos.

## Plan de tareas (en orden)
1. Confirmar la lista cruda de pendientes contra las specs 003, 005, 007, 008, 009, 010, 011 y 012 ("Fuera del alcance" y `grep -n '013'`, ya recopilados en esta vuelta, sin releer las specs completas de nuevo).
2. Consolidar `docs/arquitectura-backend.md` sobre lo que dejaron los slices.
3. Consolidar `docs/arquitectura-frontend.md` de la misma forma.
4. `README.md`: Estado, Correr local, Deploy, Verificar protección y cumplimiento, atribución de fuentes.
5. `docs/pitch.md`: guion cronometrado + lista "qué es real y qué es simulado".
6. Una vuelta del `advisor` sobre los 4 documentos.
7. Aplicar las correcciones del `advisor`.

## Riesgos
- **El contenido se desactualiza apenas algo cambie después del evento:** aceptado — es documentación de cierre, no viva.
- **Los números de CPL/CPQL en el guion pueden no existir todavía** al momento de escribir esta spec, si no corrió una búsqueda real: se marcan "ejemplo del fixture" y se reemplazan el domingo con los reales, sin tocar la estructura del guion.
- **El tiempo se acaba antes de escribir los 4 documentos:** ver orden de corte.

**Orden de corte**, si no alcanza el tiempo:
1. La consolidación de `docs/arquitectura-frontend.md`: queda lo que escribieron los slices, sin reordenar. Dapta ve el front en vivo durante la demo.
2. La consolidación de detalle de `docs/arquitectura-backend.md`: queda lo de los slices, más hexagonal y puertos.
3. La sección "Deploy" del README: el equipo ya sabe deployar, no es lo que lee el jurado.

**Nunca se cortan:** `docs/pitch.md` (guion + "qué es real y qué es simulado") — es lo único que el jurado ve directamente. Tampoco la atribución de OSM y datos.gov.co en el README: es obligación de licencia (ODbL), no documentación opcional.
