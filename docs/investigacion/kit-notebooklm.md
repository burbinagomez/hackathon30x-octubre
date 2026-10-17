# Kit de investigación NotebookLM — Reto Dapta (30X)
### Más leads, menor costo · 16 oct 2026

**Objetivo:** llegar al PRD con (a) fuentes gratuitas legalmente limpias ya elegidas, (b) un modelo de costos defendible para CPL/CPQL, (c) benchmarks de respuesta por canal, (d) qué hicieron otros fuera de LATAM y qué les falló.

---

## 0. Lo que YA está verificado (no lo vuelvas a investigar)

**Registro mercantil abierto de Colombia (datos.gov.co / RUES, Confecámaras)**
- Dataset nacional "Establecimientos - Agencias - Sucursales" (`nb3d-v3n7`): 25 columnas, **mensual**, licencia **CC BY-SA 4.0**. Trae `razon_social`, `estado_matricula`, CIIU primario/secundario, `nit_propietario`, `camara_comercio`, `categoria_matricula`, fechas de matrícula/renovación/cancelación.
- **NO trae teléfono, correo, dirección ni municipio exacto** (solo la cámara regional).
- Hay datasets por cámara (Bucaramanga `wf53-j577`, Sincelejo `y69t-3r2t`, Manizales) con variaciones.
- → **Rol en la plataforma:** filtro de ICP (CIIU + estado activa + antigüedad) y **llave de dedup (NIT)**. No es fuente de contacto.
- → Licencia ShareAlike: la base derivada que publiques va bajo la misma licencia. Para un repo open source del hackathon, encaja.

**OpenStreetMap / Overpass API**
- Gratis, sin API key, licencia **ODbL** (permite uso comercial con atribución y share-alike de la base derivada). POIs con tags `name`, `phone`, `contact:phone`, `website`, `email`, `addr:*`, `shop`/`amenity`/`office`.
- → **Rol:** fuente de **contactabilidad** (teléfono/web) y geolocalización. Cruce con el registro por nombre difuso + ciudad.

**Google Places API:** tier gratis existe, pero sus términos restringen almacenar los datos (fuera de `place_id`) → **evitar** como fuente persistente. Scrapear Google Maps viola ToS → descartado (el brief exige respetar términos).

**LinkedIn / Instagram / Facebook:** scraping viola ToS → descartados.

**Dapta (el patrocinador):** plataforma no-code de agentes de IA (voz, texto, WhatsApp, secuencias, MCP). Su calificador es principalmente un **agente de voz que llama al lead**, pregunta caso de uso / tamaño de equipo / tiempo de decisión, puntúa contra un ICP y agenda demo si supera el umbral. Integra con HubSpot, GoHighLevel, Salesforce; tiene página de Docs e Integrations.
- → **Implicación:** para que Dapta califique, **el lead necesita teléfono**. La cobertura de teléfono por fuente se vuelve métrica.
- → El entorno de prueba y su API/webhook **hay que pedirlos a los mentores**; no están públicos.

**Jev (evals):** ya investigado; ver `30x-plan-de-ataque.md` → "Evals con Jev".

---

## 1. Fuentes para cargar en NotebookLM

Carga las URLs tal cual (NotebookLM acepta links). Agrupadas por lo que responden.

### A. Qué es Dapta y cómo califica
- https://dapta.ai/es/
- https://dapta.ai/es/blog-posts/ia-calificar-leads-saas/
- https://dapta.ai/es/blog-posts/calificar-leads-por-llamadas-ia/
- https://dapta.ai/es/?p=13420 (Dapta para agentes de IA)

### B. Benchmarks de CPL por canal (fuera de LATAM)
- https://www.zeliq.com/blog/b2b-cost-per-lead
- https://expandi.io/blog/how-much-does-lead-generation-cost/
- https://axzlead.com/blog/b2b-lead-generation-cost-per-lead-by-channel-2025
- https://lead-spot.net/blog/b2b-cost-per-lead-benchmarks/
- https://prospeo.io/s/b2b-cost-per-lead
- https://saleshive.com/blog/b2b-lead-benchmarks-digital-marketing-gen

### C. Tasas de respuesta por canal (email frío vs WhatsApp)
- https://martal.ca/b2b-cold-email-statistics-lb/
- https://www.cleverly.co/blog/cold-email-benchmarks-by-industry
- https://outreaches.ai/blog/cold-outreach-benchmarks
- https://firstsales.io/blog/whatsapp-cold-outreach-b2b/
- https://sbl.so/whatsapp/whatsapp-cold-outreach-reply-rates/
- https://toflow.ai/blog/whatsapp-b2b-lead-generation

### D. Cómo lo resolvieron otros (herramientas de sourcing) y qué les falló
- https://www.zenrows.com/blog/lead-scraper
- https://phantombuster.com/blog/ai-automation/outbound-leads-scraping-tool/
- https://scrap.io/execution-time-vs-lead-based-pricing-google-maps-scraping-cost-comparison
- https://blog.apify.com/best-google-maps-scrapers/
- https://overspan.dev/blog/build-poi-dataset (POIs "gratis y legalmente" desde OSM)

### E. Fuentes de datos libres (términos y campos)
- https://www.datos.gov.co/Comercio-Industria-y-Turismo/Establecimientos-Agencias-Sucursales/nb3d-v3n7
- https://www.datos.gov.co/Estad-sticas-Nacionales/BASE-DE-DATOS-DE-EMPRESAS-CAMARA-DE-COMERCIO-DE-BU/wf53-j577/data
- https://ccmpc.org.co/datos-abiertos/
- https://publicapis.io/open-street-map-api
- https://gist.github.com/YoanSinH/64441a5626c0095c70a51bd70f364a5c (consulta RUES)

### F. Marco legal (Ley 1581, B2B)
- https://es.mailpro.com/co/ley-1581/
- https://xmslatam.com/co/habeas-data-colombia-empresas/
- https://validiti.co/tratamiento-datos-colombia-ley-1581/
- https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981 (texto de la ley)

---

## 2. Preguntas para NotebookLM (en este orden)

### Bloque 1 — Dapta (quien decide)
1. ¿Qué datos mínimos necesita el agente de Dapta para calificar un lead (teléfono, nombre, empresa, contexto)?
2. ¿Qué define Dapta como "lead calificado" y qué señales usa para puntuar?
3. ¿Por qué canal califica (llamada, WhatsApp, texto)? ¿Qué implica para el formato en que le entrego el lead?

### Bloque 2 — Modelo de costos
4. ¿Cómo calculan las fuentes el CPL cuando la fuente es orgánica/gratuita? ¿Qué componentes de costo incluyen (herramienta, tiempo humano, mensajería, enriquecimiento)?
5. ¿Qué rangos de CPL reportan por canal (email frío, WhatsApp, directorios, scraping de mapas, LinkedIn) y cómo cambian entre lead crudo y lead calificado?
6. ¿Qué herramientas cobran por tiempo de ejecución vs por lead, y qué dice eso de cómo modelar el costo de descubrimiento?

### Bloque 3 — Canales y respuesta
7. Tasa de respuesta típica de email frío B2B vs WhatsApp B2B. ¿Qué factores la mueven (personalización, hora, longitud, remitente verificado)?
8. ¿Qué señales distinguen una respuesta real de una automática o un rebote? (alimenta el clasificador de respuestas)
9. ¿Qué volumen y cadencia evitan ser marcado como spam en cada canal?

### Bloque 4 — Fuentes y legalidad
10. ¿Qué fuentes usan las herramientas de sourcing y cuáles han tenido problemas legales o de ToS? ¿Qué pasó con el scraping de Google Maps y LinkedIn?
11. Con OSM (ODbL) y datos.gov.co (CC BY-SA): ¿qué obligaciones trae usar y redistribuir una base derivada?
12. Bajo la Ley 1581: ¿el correo o teléfono de un establecimiento comercial es dato personal? ¿Qué cambia si es el celular del dueño (persona natural)? ¿Qué debe tener el primer mensaje (identificación, finalidad, opt-out)?

### Bloque 5 — Lo que falló
13. ¿Qué intentaron estas herramientas o equipos que NO funcionó (datos desactualizados, baja contactabilidad, bloqueos, costos ocultos)?
14. ¿Qué es distinto en LATAM/Colombia (WhatsApp como canal dominante, informalidad, datos de registro) que obligue a adaptar lo que funciona afuera?

### Pregunta de cierre
15. Con todo lo anterior: si solo pudiera medir UNA métrica para decidir en qué canal buscar, ¿cuál sería y por qué? (Hipótesis a confirmar: costo por lead calificado.)

---

## 3. Dónde cae cada respuesta

| Respuesta | Va a |
|---|---|
| 1-3 (Dapta) | Formato del lead, cobertura de teléfono como métrica, integración mínima del MVP |
| 4-6 (costos) | Diseño de la tabla `costos` y fórmula CPL/CPQL — el diferenciador |
| 7-9 (canales) | Plantillas del primer mensaje, clasificador de respuestas (Jev), límites de volumen |
| 10-12 (fuentes/legal) | Selección final de las 2+ fuentes, texto del mensaje, libro de cumplimiento por lead |
| 13-14 (fallos) | Lo que queda fuera del alcance; adaptaciones LATAM |
| 15 | La línea central del pitch (etapa 05) |

---

## 4. Lo que NotebookLM NO te va a dar — pedir a mentores/organizadores el día 16

- El **ICP** concreto del reto (sector, tamaño, ciudad). Sin esto el filtro es a ciegas.
- La **lista de fuentes sugeridas** (confirmar que OSM + RUES están aceptadas).
- Las **50 empresas de ejemplo** (sirven de set de prueba para dedup y encaje con ICP — y de casos para los evals).
- **Acceso y API/webhook del entorno de prueba de Dapta** (formato del lead, qué devuelve al calificar, costo por llamada del agente — necesario para CPQL).

---

## 5. Hipótesis de arquitectura de fuentes (a confirmar con la investigación)

```
RUES / datos.gov.co  ──► filtro ICP (CIIU, estado, antigüedad) + llave NIT ──┐
                                                                            ├──► tabla única de leads (dedup NIT → dominio → tel E.164 → nombre+ciudad difuso)
OSM / Overpass       ──► contactabilidad (tel, web, email, geo) ─────────────┘
Sitio web del lead   ──► enriquecimiento (email de contacto, formulario) ─── respeta robots.txt
```

Cada paso registra su costo (API, tokens, mensaje, minutos) en `costos` → CPL y CPQL salen de ahí.
