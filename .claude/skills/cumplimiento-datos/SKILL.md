---
name: cumplimiento-datos
description: Reglas de cumplimiento para encontrar, guardar y contactar leads bajo Ley 1581 (Colombia), el concepto SIC 17-96489 y los términos de cada fuente. Cárgala antes de tocar el modelo de leads, el filtro de contactabilidad, las plantillas de mensaje, el cifrado o la tabla `cumplimiento`.
---

# Cumplimiento de datos

## Base (verificada 2026-10-16)
- **Ley 1581/2012** protege datos personales de **personas naturales**. Las personas jurídicas no son "titulares": su NIT, razón social y canales genéricos (`info@`, línea comercial) no son dato personal.
- **SIC, concepto 17-96489 (2017):** los datos del registro mercantil son públicos (C. de Comercio art. 26), pero usarlos para **ofrecer productos/servicios requiere autorización** del titular cuando es persona natural. "Público" no es licencia abierta; aplican finalidad y circulación restringida.
- Un contacto **nominal** (`juan.perez@empresa.com`, celular del dueño) es dato personal de esa persona aunque la empresa sea jurídica.
- Licencias: OSM **ODbL**, datos.gov.co **CC BY-SA 4.0** → atribución + base derivada bajo la misma licencia. Croma: el usuario es responsable de la base legal; no redistribuir.
- Meta WhatsApp API: opt-in previo, plantillas de marketing con opt-out, bloqueo >2–3% → intervención.

## Reglas en el código
1. **`tipo_titular`** se determina en la ingesta desde el registro (`clase_identificacion` / `tipo_propietario`): `juridica` | `natural` | `desconocido`. `desconocido` se trata como `natural`.
2. **`contactable = tipo_titular == 'juridica' AND canal_publicado IS NOT NULL`.** Canal publicado = email o teléfono que aparece en el sitio web de la empresa o en OSM con tag de contacto del negocio. Un teléfono que solo aparece en el registro **no** es canal publicado (el registro no trae teléfono; si llegara por otra vía, igual no cuenta).
3. **Contacto nominal se descarta:** si el email tiene forma `nombre.apellido@` o el teléfono está etiquetado como personal, se guarda `razon_no_contactable = 'contacto_nominal'` y no se envía. Preferir `info@`, `ventas@`, `contacto@`, línea fija comercial.
4. **Personas naturales:** se guardan (para el embudo y la métrica "% no contactable por política"), **no se contactan**. Nunca.
5. **Fila en `cumplimiento` antes del primer envío:** `lead_id, fuente, licencia, url_origen, base_legal ('persona_juridica_canal_publicado'), as_of, opt_out_at, solicitudes[]`. Sin fila, el caso de uso de envío lanza excepción.
6. **Opt-out:** una palabra ("BAJA", "NO") o un enlace. Al recibirlo: `opt_out_at`, el lead pasa a `no_contactar`, y ningún canal vuelve a escribirle. Test obligatorio.
7. **Plantilla del primer mensaje** (email y WhatsApp), validada por test:
   - Identificación: quién escribe y en nombre de qué pyme.
   - Finalidad en una línea.
   - Origen del dato: "encontramos su contacto en su sitio web / en un directorio público".
   - Opt-out explícito.
   - <100 palabras, 1 pregunta, sin adjuntos, sin datos inventados.
   - Enlace a aviso de privacidad (`/privacidad`).
8. **Volumen:** email ≤ N/día por dominio remitente (config); WhatsApp solo con validación del dueño, ≤ M/día, y tasa de bloqueo vigilada (<1%).
9. **Cifrado:** `email`, `telefono`, `nombre_contacto`, `respuesta_texto` pasan por `Cifrador` (AES-GCM, clave en entorno) antes de persistir. Nunca en logs, trazas ni mensajes de error. Catálogo de columnas sensibles en `backend/app/seguridad/catalogo_sensibles.py`; test que falla si una columna del catálogo no está cifrada.
10. **Retención:** leads sin respuesta se purgan a los 90 días (documentado; job si hay tiempo). Respuestas: 180 días.
11. **Atribución visible:** README y pie del tablero: "Datos de OpenStreetMap (ODbL) y Confecámaras/datos.gov.co (CC BY-SA 4.0)".

## Fuentes
Permitidas: datos.gov.co (SODA), OpenStreetMap/Overpass, sitio web del lead (robots.txt, sin IPs privadas, límite de tamaño/redirecciones), Croma.
**Prohibidas** (test de `import-linter` + lista de dominios bloqueados en `web_fetch`): scraping de Google Maps, Google Places como almacén, LinkedIn, Instagram, Facebook.

## Lo que se le pregunta a los mentores (y se documenta la respuesta)
¿Se puede contactar a personas naturales comerciantes que publicaron un canal comercial? Postura por defecto: **no**. Solo cambia con instrucción escrita de los organizadores, y queda registrada en `docs/decisiones.md`.
