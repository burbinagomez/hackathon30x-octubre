---
name: fuentes-publicas
description: Cómo funciona el registro de adaptadores de fuentes (config/fuentes.yaml), los puertos FuenteDescubrimiento y Enriquecedor, y cómo consultar cada fuente permitida (Croma multi-país por endpoint, OpenStreetMap/Overpass, sitio web del lead, datos.gov.co) con sus filtros, límites, licencias y rol. Cárgala antes de escribir o tocar cualquier adaptador de fuente o el orquestador de descubrimiento.
---

# Fuentes públicas — puertos, adaptadores y registro

## Regla
Toda fuente es un **adaptador detrás de un puerto**, declarado en `config/fuentes.yaml` con `habilitado`, `paises`, `filtros`, `trae`, `tipo` (dataset/live) y `licencia`. El dominio no conoce ningún adaptador. Cambiar de fuente es un flag. **Todo adaptador pasa la suite de contrato de su puerto** (`backend/tests/contratos/`), parametrizada sobre el registro.

## Puertos
```python
class FuenteDescubrimiento(Protocol):
    meta: MetaFuente                       # paises, filtros_soportados, trae, tipo, licencia
    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas: ...
    # devuelve EmpresaCruda normalizada: pais, nombre, id_fiscal?, tipo_titular?, ciudad?, direccion?,
    # telefono?, web?, email?, actividad (código + sistema: CIIU|SCIAN|...), fuente, url_origen, as_of

class Enriquecedor(Protocol):
    meta: MetaFuente
    def enriquecer(self, lead: Lead) -> Enriquecimiento: ...   # campos que agrega + señales de calidad
```
Cada llamada recibe `RegistroCostos` y escribe su fila **antes de devolver** (skill `libro-costos`).

## Orquestador
1. Lee el registro; filtra `habilitado: true`.
2. Para el `pais` del ICP, elige adaptadores cuyos `paises` lo incluyan y cuyos `filtros` cubran los criterios. Si ninguno: reporta `sin_fuente_para(pais, criterio)` en el tablero. No inventa.
3. Ejecuta en paralelo acotado (respetando `limites`), normaliza, pasa a dedup.
4. Cobertura por país y por fuente se expone como métrica.

## Capacidades por adaptador (verificado 2026-10-17)

| Adaptador | País | Filtros | Trae | Tipo / costo | Rol |
|---|---|---|---|---|---|
| `croma_supersociedades_co` `POST /co/supersociedades/companies-search/v1` | CO | `ciiu_code` (sección/división/4 dígitos), `macrosector`, `department`, `region`, `min_revenue`, `supervision_status`, `fiscal_year`; `page`, `per_page` ≤100 | NIT, nombre, **city, address, lat/long**, CIIU, ingresos, activos, empleados, rankings, insolvencia | dataset · 1 crédito | **Descubrimiento CO principal.** Todo es persona jurídica. Sesgo: solo empresas que reportan (medianas/grandes). |
| `croma_dian_trade_co` `POST /co/dian-trade/directory-search/v1` | CO | `tariff_code` (4/6/10), `flow`, `year`, `query`; paginado ≤100 | NIT, nombre, `natural_person`, USD, kg, partidas | dataset · 1 crédito | Descubrimiento de importadores/exportadores. Sin ciudad ni contacto. |
| `croma_siem_mx` `POST /mx/siem/establishments/v1` + `/establishment/v1` | MX | `name` **(obligatorio, substring)**, `state_code` INEGI, `activity_code` SCIAN; 10/página | búsqueda: nombre, estado, cámara. **Detalle: RFC, dirección, teléfono, email, web, empleados, status** | live · 10 créditos · async (`callback_url`) | Descubrimiento MX **parcial** (hay que iterar nombres). Directorio autodeclarado. |
| `osm_overpass` | cualquiera | ciudad/área, tipo (`shop`/`amenity`/`office`/`craft`) | nombre, `phone`, `website`, `email`, `addr:*`, geo | live · cómputo | **Segunda fuente de descubrimiento (gratuita de verdad)** + contactabilidad. Cubre micro-pymes y países sin registro en Croma. |
| `datos_gov_co_rues` SODA `c82u-588k` | CO | `filtros: [ciiu, departamento]` (el adaptador traduce departamento → cámara con `config/camaras_co.yaml`). La condición de jurídica (`organizacion_juridica != 'PERSONA NATURAL'`) y `estado_matricula = 'ACTIVA'` se aplican en el servidor | `trae: [nit, nombre, ciiu, ciudad_camara]` | dataset · cómputo | **Conectado** (spec 011). Descubrimiento CO de jurídicas activas; las naturales se cuentan, no se descargan. |
| `rues_datos_gov_co` (enriquecedor, puerto `VerificadorTitular`) | CO | nombre normalizado + ciudad | `tipo_titular` + evidencia en `cumplimiento` | dataset · cómputo (`socrata_descarga`, con `lead_id`) | **Verificador de titular activo** (spec 006, enmienda 2026-10-18): reusa el cliente de `datos_gov_co_rues`; sin match único exacto en la misma ciudad queda `desconocido`. |
| `croma_rues_co` `POST /co/rues/entity-by-nit/v1` (y `entities-by-name`) | CO | NIT o nombre | matrícula, estado, CIIU, representantes, financieros, renovaciones, vinculados | live · 10 créditos | **Enriquecimiento/verificación**, no descubrimiento. Puede dar 502: reintentar con backoff. |
| `croma_supersociedades_detalle_co` | CO | NIT | accionistas, `officers[]` (representante legal), email de notificación judicial | live | Enriquecimiento. |
| `croma_sunat_pe` | PE | RUC/documento/nombre | contribuyente, estado | live | Verificación PE. |
| `sitio_web` | cualquiera | URL del lead | `mailto:`, `wa.me/`, teléfonos; prefiere genéricos (`info@`, `ventas@`) | cómputo | Contactabilidad. robots.txt, sin IPs privadas, 2 MB, 3 redirecciones, 8 s. |

**Sin descubrimiento en Croma:** BR (solo sanciones/deudas por CNPJ) y PE (SUNAT solo por RUC/nombre). Ahí descubre OSM.

## Límites y planificación
- **Croma:** ~100 requests/24 h (catálogo) y 1.500 créditos gratis/mes. Cuenta nueva para el evento. Planifica: Supersociedades con `per_page=100` → 100 requests = hasta 10.000 empresas/día. Cachea respuestas crudas en `fuente_cache` (uso propio; **no redistribuir**). Pin de versión en `as_of`.
- **Overpass:** ≤1 req/s, `[timeout:25]`, `User-Agent` identificable, área acotada.
- **SODA:** `X-App-Token`, `$limit` ≤50.000, `$order` estable.

## Normalización común (`EmpresaCruda`)
- `id_fiscal`: NIT (CO, sin DV; validar DV aparte), RFC (MX), RUC (PE), CNPJ (BR). Guardar `sistema_id`.
- `actividad`: código + `sistema` (`CIIU` CO/PE, `SCIAN` MX, `CNAE` BR). Tabla de equivalencias en `config/actividades.yaml` para el ICP multi-país.
- `telefono` → E.164 con `phonenumbers` y región del país.
- `tipo_titular`: `juridica` si viene de Supersociedades; de `natural_person` en DIAN Trade; de `legal_name` vs `person_name` en SIEM; de datos.gov.co (`c82u-588k`) por `organizacion_juridica` (`PERSONA NATURAL` = natural), **nunca** por `clase_identificacion`: la clase NIT incluye personas naturales. Si no se sabe → `desconocido` (= natural para cumplimiento).

## Dedup entre fuentes (en este orden; cada regla con test)
1. `id_fiscal` + `pais`.
2. Dominio del sitio web normalizado.
3. Teléfono E.164.
4. Nombre normalizado (sin tildes, sin sufijos societarios: S.A.S., LTDA, S.A. de C.V., S.A.C., &) + misma ciudad/departamento, trigram ≥0.85 candidato; ≥0.92 fusión; entre ambos → cola de revisión.
Un lead fusionado conserva **todas** sus fuentes en `lead_fuentes`.

## Licencias y atribución
OSM **ODbL** · datos.gov.co **CC BY-SA 4.0** · Croma: datos públicos de gobierno, usuario responsable de la base legal, **no redistribuir** sus respuestas. Atribución en README y pie del tablero.

## Prohibidas (bloqueadas por `import-linter` y lista de dominios en `web_fetch`)
Scraping de Google Maps · Google Places API como almacén · LinkedIn · Instagram · Facebook.
