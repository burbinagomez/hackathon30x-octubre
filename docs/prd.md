# PRD — Reto Dapta: Más leads, menor costo
### 30X Hackathon · 16–18 oct 2026 · v1.0 (pre-ICP)

> Una página de PRD (lo que Sandra pidió) + anexos de diseño. Lo marcado **[MENTORES]** depende de documentos que aún no tenemos (ICP, fuentes sugeridas, 50 empresas, API de Dapta). El PRD se cierra en cuanto lleguen; mientras, se construye lo que no depende de ellos.

---

## 1. Mini PRD (una página)

**El problema en tres líneas.** Las pymes que llegan a Dapta dependen de pauta ($80–500 USD por lead según la fuente), no saben en qué canal buscar y no miden cuánto les cuesta cada lead. 3 de cada 5 piden a Dapta que les consiga los leads, no solo que los convierta. Dapta no tiene esa capa.

**Para quién.**
- *Usuaria:* la pyme (dueño o encargado de marketing) que hoy paga pauta a ciegas.
- *Quien decide:* producto/growth de Dapta. Responde por **leads calificados**, no por leads. El pitch se le habla a esa persona.

**Flujo principal (3 pasos).**
1. **Encontrar.** La usuaria define el ICP → la plataforma consulta ≥2 fuentes públicas y gratuitas (registro mercantil abierto + OpenStreetMap + sitio web del negocio) → deduplica (NIT → dominio → teléfono E.164 → nombre+ciudad difuso) → filtra por ICP y por **política de datos** (solo personas jurídicas con canal comercial publicado) → una sola tabla de leads, cada uno con su fuente y su base legal.
2. **Contactar.** Primer mensaje por el canal que publicó el lead (email primero; WhatsApp solo a números publicados como comerciales) → se registra envío, entrega, respuesta y bloqueo → la respuesta se clasifica en tiempo real (interesado / no / automática / rebote) y se notifica.
3. **Medir.** Tablero por fuente y por canal: encontrados → únicos → ICP → contactables → contactados → respondieron → **calificados por Dapta**, con **costo total, CPL y CPQL**. Cada operación del pipeline registra su costo real en un libro mayor; los indicadores salen de ahí, no de una estimación.

**Terminado cuando** (el test que hoy falla): con el ICP cargado, la plataforma encuentra leads reales en ≥2 fuentes durante el evento, los contacta, registra al menos una respuesta real, y el tablero muestra CPL y CPQL por fuente y canal con el costo trazable operación por operación.

**Fuera del alcance.** Cerrar ventas. CRM. Secuencias multi-toque. Llamadas propias (las hace Dapta). LinkedIn, Instagram, Facebook, Google Maps (ToS). Personas naturales comerciantes como destinatarias de outreach. Pauta. Onboarding self-service de pymes y multi-tenant completo (el reto entrega **un** ICP; el sistema queda preparado por `tenant_id`, pero no se construye registro ni facturación).

### 1b. Recorrido del usuario (lo que se ve en el demo)

El reto **entrega el ICP**; no hay un cliente externo que "pida". En el evento, la usuaria es la pyme (o Dapta operando por ella) y el ICP viene precargado como primera búsqueda.

**Patrón tomado de los referentes** (Artisan, Apollo, Clay — ver §2b): ICP → filtros → vista previa → lista → quitar malos → aprobar mensajes → enviar. Tres puertas de entrada que convergen en el mismo formulario prellenado:

1. **Nueva búsqueda — tres puertas, un formulario:**
   - **Puerta A · "Empresas que ya me compran"** (lookalike, como Apollo/Clay): pega 5–50 clientes o usa **las 50 empresas de ejemplo del reto** → se resuelven por nombre en RUES vía Croma → distribución de CIIU, ciudades y tamaño → **filtros prellenados**.
   - **Puerta B · "Describe en una frase a quién le vendes y qué ofreces"** (como Artisan, pero en un solo turno): una llamada al LLM con salida estructurada → los mismos filtros prellenados. Es el único "agente" de intake; no es un chat largo.
   - **Puerta C · Filtros directos:** país · actividad/sector · ciudad o departamento · tamaño · palabras clave · exclusiones.
   El formulario común añade: canal preferido · tope de gasto · mensaje base (quién soy, qué ofrezco).
   **Vista previa antes de buscar:** cuántas empresas coinciden por fuente (Supersociedades devuelve `total`; Overpass `out count`) y **costo estimado** (créditos Croma + cómputo) — lo que Clay hace con el conteo, más el costo que Clay no te dice. Botón **Buscar**.
2. **La plataforma trabaja sola:** el orquestador elige los adaptadores habilitados que cubren el país/criterios, consulta, normaliza, deduplica, filtra por ICP y por política de datos, enriquece, y muestra el embudo en vivo con su costo acumulado.
3. **Revisión:** tabla de leads contactables (con fuente, score de calidad, canal publicado, base legal); la usuaria **quita los que no encajan** (Artisan). Los primeros mensajes, generados desde el mensaje base, quedan en **"pendiente de aprobación"** (modo copiloto de Artisan) hasta que la usuaria aprueba.
4. **Envío y respuestas:** la plataforma envía, registra entrega/respuesta/bloqueo, clasifica cada respuesta en tiempo real y notifica los "interesado".
5. **Calificación:** los interesados con teléfono se exportan/envían a Dapta; los resultados vuelven y cierran el embudo.
6. **Tablero:** por fuente y por canal, embudo + tasas + **CPL y CPQL**. Es la pantalla del pitch.

**Buscar no lo hace un agente de IA navegando:** lo hacen adaptadores deterministas contra APIs. Es más barato, reproducible y auditable — que es el punto del libro de costos. La IA entra solo donde hay juicio difuso: encaje con el ICP, clasificar respuestas, redactar el mensaje.

**Opcional (slice de cierre):** captura conversacional del ICP — "cuéntame a quién le vendes" → el agente propone los campos del formulario → la usuaria confirma. Le habla a la audiencia de Dapta (agentes de IA), pero no es núcleo.

---

## 2. Lo que la investigación fijó (y por qué)

| Hallazgo | Fuente | Decisión de diseño |
|---|---|---|
| Dapta califica con **agente de voz**: sin teléfono no hay calificación. "Calificado" = supera umbral de ICP + **demo agendada**. | Dapta | Lead sin teléfono = `no_calificable`. **CPQL = costo total / demos agendadas.** Cobertura de teléfono por fuente es métrica. |
| **Croma** (API de registros de gobierno, multi-país: CO 33 fuentes, MX 17, PE 10, BR 8, US 6). **Endpoints con filtros que sirven para descubrir:** Supersociedades CO `companies-search` (CIIU, macrosector, departamento, ingresos → NIT, nombre, **ciudad, dirección**, geo, financieros, empleados; dataset = 1 crédito); DIAN Trade CO `directory-search` (partida arancelaria, flujo, año → NIT, nombre, USD); SIEM MX `establishments` (estado + SCIAN, nombre obligatorio → detalle con **teléfono, email, web**). **Solo verificación:** RUES CO y SUNAT PE (por nombre/NIT). **BR sin registro de empresas.** Límites: ~100 req/24h, 1.500 créditos gratis. Términos: usuario responsable de la base legal; no redistribuir. | docs.usecroma.com, api.croma.run/catalog | **Origen de datos principal esta vez (ENCONTRAR), multi-país**, vía adaptadores por endpoint. Supersociedades = todo persona jurídica (cumplimiento resuelto de origen), pero **sesgo a empresas que reportan** (medianas/grandes). Cada consulta al libro de costos. |
| Registro mercantil abierto (datos.gov.co, Confecámaras, mensual, CC BY-SA 4.0): NIT, razón social, CIIU, estado, tipo de propietario — **sin teléfono/correo/dirección**. | datos.gov.co `nb3d-v3n7` | Adaptador construido y **desconectado por config** (`habilitado: false`). Un flag lo vuelve a conectar si el jurado objeta Croma como "gratuita" o si se agota el tier. |
| OSM/Overpass (ODbL, sin key): POIs con `phone`, `website`, `email`, `addr:*`, cualquier país. | OSM | **Segunda fuente de descubrimiento (la gratuita de verdad)** y fuente de **contactabilidad**; cubre micro-pymes que no están en Supersociedades y países sin registro en Croma (BR, PE). Cruce con registro por nombre difuso + ciudad. |
| **SIC 17-96489:** datos del registro son públicos pero usarlos para ofrecer productos requiere autorización del titular; Ley 1581 solo protege **personas naturales**. | SIC (concepto no vinculante) | **Outreach solo a personas jurídicas**, por canales que ellas publicaron. Personas naturales: visibles en tablero, no contactadas. Libro de cumplimiento por lead. |
| Google Places restringe almacenar datos; scrapear Maps/LinkedIn/Instagram viola ToS. | ToS | Descartados. |
| CPL crudo B2B: email frío $25–120; pauta $80–500. Conversión a calificado ≈ 10%; **CPQL = 4–10x el CPL**. | AxzLead, Zeliq, investigación NotebookLM | El tablero muestra CPL y CPQL lado a lado: un canal barato que no califica es caro. |
| Email frío: respuesta 3–5%. WhatsApp: apertura 90–98%, respuesta frío 3–10% (10–20% personalizado en LATAM). | Outreaches, SBL | Email = primer toque; WhatsApp acotado. |
| Responder en <90 s multiplica ~4x las demos vs >30 min. | SBL | Clasificación de respuestas **en tiempo real**, no batch. |
| WhatsApp API: exige opt-in, plantillas de marketing con opt-out, bloqueos >2–3% → intervención de Meta. | SBL / Meta | WhatsApp solo a números comerciales publicados, volumen bajo, **tasa de bloqueo en el tablero** (<1%). |
| Secuencias de 3+ canales → +287% respuestas. | Outreaches | Fuera del alcance del MVP; se menciona como siguiente paso en el pitch. |

---

## 2b. Precedentes — quién ya resolvió qué, y qué nos llevamos

| Quién | Qué resolvió y cómo | Qué le falló | Qué nos llevamos |
|---|---|---|---|
| **Clay** (waterfall enrichment, EE.UU.) | Encadena +100 proveedores de datos en orden; **cobra solo por el proveedor que acierta**; mide por proveedor la tasa de acierto y el **costo por hit**, y ordena la cadena por costo por hit ascendente. "Costo por contacto verificado = gasto total ÷ contactos verificados". | **Costo impredecible** (queja #1 de sus usuarios); reordenar la cadena cambió la factura **4.1x con la misma cobertura**; más proveedores no mejora precisión, solo cobertura; techo de rendimiento a los 5–7 proveedores. | Es nuestro libro de costos aplicado a fuentes de pago. Nosotros lo hacemos con fuentes gratuitas: **costo por hit por fuente**, orden por costo por lead *usable*, tope de gasto por lead, y verificación antes de enviar. |
| **AI SDRs** (11x, Artisan, AiSDR, Regie) | Outbound automatizado con bases de datos propias. $250–2.500/mes. Costo modelado por reunión $88–125 vs $533 un SDR humano. | Ninguno usa fuentes gratuitas ni publica resultados reales. Falla principal: **calidad de lista → automatizan rebotes con confianza y queman el dominio**. La narrativa "SDR 100% autónomo" tocó techo en 2024–25; 11x relanzó. | No vendemos "SDR con IA"; vendemos **medición**. La IA clasifica y redacta; la decisión la toma el número. Verificar antes de enviar es obligatorio. |
| **Industria de datos de prospección** (Apollo, ZoomInfo, Lusha, Seamless…) | Bases compradas + LinkedIn scrapeado. | Un solo proveedor cubre 50–60%; las cascadas prometen 80–92% pero un benchmark independiente de 20k contactos dio **48% usable**. Los datos decaen **~22% al año** (hasta 2%/semana). Todos scrapean las mismas fuentes → "los mismos contactos que golpean otros 50 SDRs". Gmail/Yahoo exigen <0.3% de quejas de spam. | Nuestra ventaja es **frescura y no solapamiento**: registro mercantil mensual, OSM y Croma en vivo, y nadie está golpeando a las pymes desde ahí. Métrica = **tasa usable**, no tasa de match. Cada lead lleva `as_of`. |
| **LinkedIn** (crackdown 2025) | — | Apollo, Evaboot, Seamless y LGM removidos; extensiones discontinuadas; cuentas de usuarios en riesgo; demandas (Mantheos, hiQ). La responsabilidad recae en el negocio aunque scrapee un tercero. | Valida excluir LinkedIn. En el pitch: "las fuentes que usamos no pueden desaparecer por un cambio de ToS". |
| **Leadsales** (México → CO, PE; 1.400 clientes, US$1.6M ARR, seed US$3.7M) | CRM nativo de WhatsApp para pymes LATAM: organiza y automatiza chats con leads que ya llegaron. | Resuelve **gestión** de leads, no **adquisición**. Mismo hueco que ve Dapta: 3 de 5 pymes piden que les consigan los leads. | La capa "encontrar en fuentes gratuitas + medir CPL/CPQL" está **abierta en LATAM**. WhatsApp-nativo importa, pero con las reglas de Meta. |

| **Patrón de entrada del usuario** (Artisan · Apollo · Clay) | Artisan: chat de onboarding ~10 min (países, industrias, cargos, tamaño; resumen de una frase, features, dolores, pruebas; tono) → llena leads sola → el usuario quita malos → emails en "pendiente de aprobación". Apollo: formulario de filtros (tamaño, industria, ubicación, ingresos) → búsqueda guardada → lookalikes desde una cuenta → secuencia. Clay: "Find Companies" con filtros → **vista previa de cuántas coinciden antes de gastar créditos** → importar; lookalikes e importar CSV. | Ninguno pide programar ni "crear un agente". Clay: costo impredecible pese al conteo previo. Apollo: el usuario debe traducir su ICP a filtros a mano. | Tres puertas (lookalike desde clientes/las 50 de ejemplo · una frase → ICP · filtros) que convergen en **un formulario prellenado**; **vista previa con conteo y costo estimado**; lista para quitar malos; mensajes en pendiente de aprobación. |

**Lo que nadie de la lista hace y nosotros sí:** fuentes públicas gratuitas (no bases compradas), costo real por operación (no estimado) **y costo estimado antes de buscar**, filtro de persona jurídica por cumplimiento, y CPQL cerrado con el calificador de Dapta.

---

## 3. Arquitectura hexagonal: puertos, adaptadores y registro

**Principio:** toda entrada y salida externa es un adaptador detrás de un puerto del dominio, y **se conecta o desconecta en `config/fuentes.yaml`**, nunca tocando dominio ni casos de uso. Cada adaptador declara `paises`, `filtros` que soporta y `trae` (qué campos devuelve); el orquestador elige los habilitados que cubren el ICP y, si ninguno cubre un país/criterio, lo reporta.

```
PUERTOS (dominio)            ADAPTADORES (infraestructura) — config/fuentes.yaml
─────────────────────────    ────────────────────────────────────────────────────────────────
FuenteDescubrimiento   ◄──   croma_supersociedades_co  (CO · CIIU/dpto/ingresos → NIT, ciudad, dirección)   [ON]
                             croma_dian_trade_co       (CO · partida arancelaria → NIT, nombre)              [ON]
                             croma_siem_mx             (MX · estado + SCIAN → detalle con tel/email)        [OFF hasta ICP MX]
                             osm_overpass              (cualquier país · ciudad + tipo → tel, web, geo)      [ON]
                             datos_gov_co_rues         (CO · CIIU/cámara → NIT, tipo_titular)               [OFF esta vez]
Enriquecedor           ◄──   croma_rues_co · croma_supersociedades_detalle_co · croma_sunat_pe · sitio_web
CanalContacto          ◄──   smtp_email [ON] · whatsapp_meta [OFF hasta validar]
Calificador            ◄──   dapta_api [OFF hasta doc] · dapta_csv [ON]
Clasificador           ◄──   jev (jev-1.13.0)
RegistroCostos         ◄──   postgres_costos
```

**Flujo de datos:**
```
FuenteDescubrimiento (N adaptadores, por país) ─► normalización común ─► dedup (NIT → dominio → tel E.164 → nombre+ciudad) ─► filtro ICP + política de datos ─► leads
leads ─► Enriquecedor (verifica matrícula/tipo_titular, trae contacto publicado, score de calidad) ─► contactables
contactables ─► CanalContacto ─► respuesta ─► Clasificador ─► Calificador (Dapta) ─► calificaciones
todo adaptador ─► RegistroCostos ─► costos ─► tablero (CPL, CPQL)
```

**Suite de contrato por puerto** (`backend/tests/contratos/`): un solo archivo de tests por puerto, parametrizado sobre todos los adaptadores del registro, con proveedor falso. Un adaptador nuevo se agrega al YAML y debe pasar la suite; si no, no existe.

**Multi-país:** el ICP lleva `pais`. Cobertura hoy: **CO** descubrimiento completo (Croma Supersociedades + DIAN Trade + OSM); **MX** parcial (SIEM + OSM); **PE/BR** solo OSM + verificación. La cobertura por país se muestra en el tablero, no se esconde.

**Roles:** Croma (multi-país) + OSM = descubrimiento · sitio web + Croma detalle = contactabilidad y verificación · SMTP = canal · Dapta = calificación · `costos` = medición.

**Dedup (en este orden, cada regla con su test):** NIT exacto → dominio normalizado → teléfono E.164 → nombre normalizado + ciudad con similitud ≥ umbral (trigram). Un lead conserva **todas** sus fuentes (`lead_fuentes`) para atribuir costo y para la métrica "qué fuente lo encontró primero / lo encontró sola".

**Tablas núcleo (multi-tenant, RLS por `tenant_id`):**
- `tenants`, `busquedas` (una por ICP: país, criterios, canal preferido, tope de gasto, mensaje base, estado) — el tablero pivota por búsqueda
- `leads` (datos de empresa; campos de contacto **cifrados**; `tipo_titular` jurídica/natural; `contactable` bool + `razon_no_contactable`)
- `lead_fuentes` (lead × fuente, `encontrado_en`, `licencia`, `url_origen`)
- `contactos` (envíos: canal, plantilla, ts, estado entrega, `respuesta_texto` cifrado, `clasificacion`, `bloqueo`)
- `calificaciones` (respuesta de Dapta: score, demo agendada, ts, costo de llamada)
- `costos` (**el libro mayor**, ver §4)
- `cumplimiento` (por lead: base legal, fuente, licencia, fecha, opt-out, solicitudes del titular)

---

## 4. Modelo de costos (el diferenciador)

**Principio:** la fuente es gratis; el lead no. Cada operación escribe una fila en `costos` en el momento en que ocurre.

| `tipo_operacion` | Unidad | Costo unitario | Atribución |
|---|---|---|---|
| `socrata_descarga` | segundos de cómputo | tarifa Railway/seg (config) | prorrateado entre leads producidos por la corrida |
| `overpass_query` | segundos + bytes | idem | prorrateado |
| `web_fetch` | request | cómputo + ancho de banda | al lead |
| `croma_consulta` | créditos (1 dataset / 10 live) | precio del plan ÷ créditos (tier gratis = $0 con nota del valor de lista) | al lead |
| `llm_tokens` (enriquecimiento, redacción) | tokens in/out | precio del modelo | al lead |
| `jev_call` (clasificación respuesta / encaje ICP) | tokens | $0.042/M in | al lead |
| `email_envio` | mensaje | proveedor SMTP con tier gratuito creado para el evento (≈$0 a este volumen; nota de costo de dominio/calentamiento al escalar) | al lead |
| `whatsapp_plantilla` | mensaje | tarifa Meta Colombia (config) — canal **[VALIDAR]** | al lead |
| `dapta_llamada` | minutos | tarifa del entorno de prueba **[MENTORES]** | al lead |
| `minutos_humanos` | minutos | tarifa configurable | al lead o prorrateado |

**Fórmulas (todas desde `costos`):**
- `CPL(fuente) = Σ costos atribuidos a la fuente / leads únicos ICP de esa fuente`
- `costo_por_respuesta(canal) = Σ costos (descubrimiento prorrateado + contacto) / respuestas reales`
- `CPQL(fuente, canal) = Σ costos (descubrimiento + contacto + llamada Dapta) / demos agendadas`
- Tasas: respuesta, bloqueo, calificación, cobertura de teléfono, % contactable por política.

Las tarifas viven en `config/tarifas.yaml` (versionado) para que el jurado vea los supuestos.

---

## 5. Contacto y cumplimiento

**Quién se contacta:** solo `tipo_titular = jurídica` **y** canal publicado por la empresa (web, OSM con tag de contacto, o WhatsApp comercial publicado). Todo lo demás se encuentra y se muestra, no se contacta.

**Primer mensaje (email y WhatsApp):** identificación del remitente y de la pyme usuaria, finalidad en una línea, de dónde salió el contacto ("su sitio web / directorio público"), **opt-out en un clic/una palabra**, enlace a aviso de privacidad. <100 palabras, 1 pregunta. Sin adjuntos.

**Libro de cumplimiento (`cumplimiento`):** por lead, la fuente, la licencia (ODbL / CC BY-SA), la base legal (persona jurídica + canal publicado), la fecha, y cualquier opt-out o solicitud. Exportable. Es la respuesta al requisito "respetando los términos de cada fuente y la ley de protección de datos", y una pantalla del demo.

**Licencias:** atribución a OpenStreetMap y a Confecámaras/datos.gov.co en README y en el tablero; la base derivada publicada bajo ODbL / CC BY-SA (compatible con el repo open source del evento).

**Datos sensibles:** teléfonos, correos y textos de respuesta cifrados en reposo; nunca en logs. RLS por tenant con test que intenta romper el aislamiento. Secrets en variables de Railway (`api`) y en el GitHub Environment `produccion` (migraciones); ninguna key de Supabase en el runtime.

---

## 6. IA en el pipeline (y sus evals)

| Uso | Cómo | Eval |
|---|---|---|
| Encaje con ICP (señales difusas: "¿este negocio es del rubro X?") | `jev_classify` con preguntas estrechas + opción "ninguna"; lo determinista (CIIU, estado) va por reglas | Eval `encaje_icp` del harness (§6b), dataset de pymes reales + las 50 empresas **[MENTORES]** |
| Clasificación de respuestas | `jev_check` en tiempo real: ¿interesado? ¿rechazo? ¿automática? ¿rebote? ¿pide no contacto? | Eval `clasificacion_respuestas` (§6b): 20–30 respuestas sintéticas + las reales del evento; umbral ≥90% |
| Redacción/personalización del primer mensaje | LLM (Sonnet vía harness) con plantilla fija + 1 dato del lead; salida validada (longitud, opt-out presente, sin datos inventados) | Eval `pertinencia_mensaje` (§6b): scorers de forma + juez 0–1, PASS^3 |

Versión de Jev pineada (`TYPESAFE_DEFAULT_MODEL=jev-1.13.0`). Todo entra a `costos`.

---

## 6b. Evals — lo que no se mide no se declara funcionando

**Ciclo:** casos → agente → scorers → baseline → PR verde/rojo.
1. **Casos** (`backend/evals/dataset.json`): pymes reales, cada una con su origen (fuente + `as_of`) y una etiqueta humana (`encaja` / `no_encaja`; y, cuando exista, el resultado de Dapta).
2. **Agente:** el componente bajo prueba corre sobre cada caso (clasificador de encaje, redactor del mensaje, clasificador de respuestas).
3. **Scorers**, de dos tipos:
   - **Forma** — código determinista en Python, pasa o no pasa: ¿salida con el esquema esperado?, ¿etiqueta dentro del enum?, ¿<100 palabras?, ¿opt-out?, ¿origen del dato?, ¿una sola pregunta?
   - **Significado** — un juez que devuelve una probabilidad 0–1: Jev (`jev_check` / `jev_classify`) o LLM-as-judge con un prompt versionado en `backend/evals/jueces/`. ¿Encaja con el ICP? ¿El mensaje es pertinente para *este* lead? ¿Inventa datos?
4. **Baseline** (`backend/evals/baseline.json`, versionado): el número agregado por eval de la última versión aceptada.
5. **PR verde/rojo:** si un agregado baja respecto al baseline o queda bajo su umbral, el runner sale ≠ 0 y el PR queda rojo. Si mejora, el baseline se actualiza en el mismo PR.

**PASS^K con k=3:** todo componente no determinista (LLM-as-judge, redacción del mensaje) corre 3 veces por caso, y el caso pasa solo si pasa las 3. Jev baja a k=1 solo después de demostrar con k=3, sobre el set, que siempre da la misma respuesta.

**Runner:** `cd backend && uv run python -m evals.run` corre local con un comando y devuelve el número agregado por eval y la lista de casos fallidos. CI invoca el mismo comando. Este fin de semana no se usan Braintrust ni Actions: el chequeo es el comando local más el baseline commiteado.

**Los 3 puntos de decisión que se evalúan:**

| Decisión | Componente | Forma | Significado | Ground truth |
|---|---|---|---|---|
| **Encaje con ICP** (eval `encaje_icp`) | `jev_classify` (slice 6) | etiqueta ∈ {encaja, no_encaja, ninguna} | probabilidad de encaje vs etiqueta humana | etiqueta en `dataset.json` |
| **Pertinencia del mensaje** (eval `pertinencia_mensaje`) | redactor Sonnet (slice 7) | <100 palabras, opt-out, origen, 1 pregunta, sin adjuntos | juez 0–1: pertinente para este lead, sin datos inventados | muestra revisada por un humano |
| **Match con Dapta** (eval `match_dapta`) | encaje predicho vs calificación (slice 8) | resultado de Dapta ∈ enum | — | **la calificación de Dapta**: ¿los que marcamos `encaja` son los que Dapta califica? |

---

## 7. Tablero (lo que ve el jurado)

Por **fuente** (RUES, OSM, web) y por **canal** (email, WhatsApp), con pivote:
encontrados · únicos · ICP · con teléfono · contactables · contactados · entregados · respondieron · bloqueos · calificados (Dapta) · **costo total · CPL · CPQL** · tasa de respuesta · tasa de calificación · % no contactable por política de datos.

Más: embudo por fuente, línea de tiempo de costos del evento, y la pantalla de cumplimiento por lead.

---

## 8. Integración con Dapta

**[MENTORES]** formato del lead, endpoint/webhook, qué devuelve al calificar, costo por llamada. Diseño por puertos: `PuertoCalificador` con adaptador `DaptaAPI` cuando tengamos la doc, y adaptador `DaptaCSV` (exportar leads con teléfono + importar resultados) como respaldo si la API no llega a tiempo. El CPQL se calcula igual con cualquiera.

---

## 9. Orden de construcción (slices, TDD, un flujo completo primero)

1. **Walking skeleton**: back `/health` y front en blanco en Railway, Postgres en Supabase, CI verde, secrets fuera, import-linter. *(sáb AM)*
2. **Puertos + registro + primer adaptador:** puerto `FuenteDescubrimiento`, carga de `config/fuentes.yaml`, suite de contrato, adaptador `croma_supersociedades_co` → `leads` con ICP (CIIU/dpto) y `tipo_titular=juridica` → test rojo de dedup por NIT y test de contrato. *(sáb AM/PM)*
3. **Segundo adaptador: `osm_overpass`** → normalización común + match difuso + dedup teléfono/dominio → los 4 niveles de dedup con tests; `croma_dian_trade_co` si sobra tiempo. *(sáb PM)*
4. **Evals harness** (§6b): `backend/evals/dataset.json` con 20–40 pymes reales (origen + etiqueta encaja/no encaja), armado con las que encuentran 2 y 3 y con las 50 de ejemplo cuando lleguen; scorers de forma en Python; prompt de juez que puntúa encaje y calidad de mensaje (0–1); runner k=3 que devuelve el número agregado y la lista de casos fallidos; `baseline.json` guardado para comparar. Sin Braintrust ni Actions este fin de semana. *(sáb PM, ~2 h)*
5. **Libro de costos** (`RegistroCostos` + Croma créditos + cómputo) + CPL por fuente en el tablero + **formulario "Nueva búsqueda" (puerta C) con vista previa de conteo y costo estimado**. *(sáb PM)* ← con esto ya hay demo mostrable
6. **Enriquecedor:** `sitio_web` (contacto publicado) + `croma_rues_co` (verificación, tipo_titular) → `contactable`. *(sáb noche)*
7. **Email** vía `CanalContacto` + adaptador SMTP (proveedor gratuito nuevo; nada de otros proyectos) + respuestas por IMAP/webhook + `jev_check` en tiempo real + tasa de respuesta. *(dom AM)*
8. **Dapta** (`dapta_csv` primero; `dapta_api` si llega la doc) + CPQL. *(dom AM)*
9. **WhatsApp** (`whatsapp_meta`, acotado, tasa de bloqueo) — **[VALIDAR]**; si no se valida, el MVP es solo email. *(dom, si hay tiempo)*
10. **Puertas A y B de intake:** lookalike desde las 50 empresas de ejemplo (resolver por nombre en RUES → ICP prellenado) y "una frase → ICP" (una llamada LLM con salida estructurada, validada por `jev_check`). *(dom, si hay tiempo; es el remate del pitch para la audiencia de Dapta)*
11. **`datos_gov_co_rues`** como adaptador desconectado con su test de contrato pasando — demuestra en vivo el "se conecta y desconecta". *(dom, si hay tiempo; 1 h)*
12. **Seguridad**: RLS probado, cifrado de contacto, libro de cumplimiento, `/security-review`. *(transversal desde el slice 2, cierre dom PM)*
13. README + arquitectura + video de respaldo (Cap) + pitch. *(dom PM)*

El número del slice es el de su spec (`specs/0NN-…`). Si el domingo a las 3pm no está el 9, se corta: email solo. Un flujo completo vale más que dos a medias.

---

## 10. Pitch (etapa 05, para quien decide en Dapta)

**Rúbrica del 30X** (con esto se juzga, y con esto se ordena el pitch):

| Criterio | Peso | Evidencia nuestra |
|---|---|---|
| Impacto | 30% | CPL y CPQL reales por fuente y canal, contra $80–500 por lead en pauta |
| Innovación | 20% | fuentes públicas gratuitas, costo estimado antes de buscar, CPQL cerrado con el calificador de Dapta |
| Viabilidad técnica | 20% | evals con baseline y PASS^3 (§6b), hexagonal con suite de contrato, CI |
| Viabilidad de implementación | 20% | adaptadores por flag, RLS, cifrado, libro de cumplimiento, costo mensual estimado |
| Presentación | 10% | demo en vivo del tablero + video de respaldo |

1. **Problema:** sus pymes pagan $80–500 por lead en pauta y no saben qué canal les sirve; 3 de 5 le piden leads.
2. **Solución en acción:** demo del tablero con leads reales del fin de semana, CPL y CPQL por fuente y canal, y el libro de costos abierto.
3. **Impacto:** "qué canal trae leads baratos y cuál trae leads buenos" — con número, no con opinión. Y el hallazgo honesto: el canal con mejor respuesta (WhatsApp) es el de mayor riesgo regulatorio; lo medimos.
   *Respaldo:* "Clay ya cobra así por fuente y es la referencia de la industria; nosotros aplicamos ese modelo a fuentes gratuitas. La industria de datos sufre de bases viejas (decaen ~22%/año) y solapadas; las nuestras son frescas y nadie más las golpea. Leadsales levantó US$3.7M resolviendo la gestión de leads por WhatsApp en LATAM — la adquisición sigue abierta."
4. **Qué se necesita para implementarlo:** piloto con 1 pyme real, conectado a la API de Dapta, ya con RLS, cifrado, cumplimiento por lead, costo mensual estimado y evals en CI.

---

## 11. Pendientes **[MENTORES]** — pedir hoy

- ICP del reto (sector, tamaño, ciudad). Hasta entonces: ICP de prueba configurable.
- Lista de fuentes sugeridas (confirmar RUES + OSM).
- Las 50 empresas (set de prueba de dedup/ICP y casos de eval).
- Acceso, formato y costo del entorno de Dapta.
- ¿Se puede contactar a personas naturales comerciantes si publicaron un canal comercial? (Nuestra postura: no, salvo instrucción expresa; lo documentamos.)

## 12. Regla del proyecto

**Nada de otros proyectos entra aquí.** Cuentas, proveedores, código o credenciales de otros proyectos del equipo no se reutilizan. Todo servicio externo (SMTP, WhatsApp, base de datos, CI) se crea nuevo para el evento. Única excepción posible: un proveedor de WhatsApp Business API ya existente, **solo si el dueño lo valida**; mientras tanto el canal se trata como no disponible.
