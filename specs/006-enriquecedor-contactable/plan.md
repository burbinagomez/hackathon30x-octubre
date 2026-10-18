# Implementation Plan: 006 — Enriquecedor (`sitio_web` + `croma_rues_co`), `contactable` y `jev_classify`

**Branch**: `feature/006-enriquecedor-contactable` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Re-verificado contra `origin/main` en **550928d** (merge del PR #40, `feature/005-api`), que es posterior al 5584710 (#39) que se pidió. Entre los dos solo entraron la autenticación con Supabase Auth y `GET /usuarios/me`; no entró ninguna migración. La spec da por hechas cosas de la 002, la 003, la 004 y la 005 que **todavía no están en `main`**. Cada una tiene un ID (D1…D11) en "Dependencias externas", con el estado leído del árbol, no de los planes. Una tarea que depende de una D ausente queda bloqueada hasta que llegue la D o salvo que una decisión de Daniel (Pn) la resuelva dentro de la 006. No se reimplementa acá lo que es de otro slice.
>
> **La migración es la 0008.** La spec (`spec.md:151` y `:158`) nombra `0005_enriquecimiento.sql`, pero ese número quedó viejo. En `main` están la 0001, 0002, 0003, 0005 (`validar_checks_leads`) y 0006 (`libro_costos_busqueda`, #38). La 0007 queda reservada para la 012. El DDL de abajo es una **propuesta**: no existe ningún archivo en `supabase/migrations/` hasta que Daniel lo apruebe.
>
> Artefactos: igual que en la 005, este slice entrega solo `plan.md` y `tasks.md`.

## Summary

La 006 entrega:
- el módulo `enriquecimiento`, con dominio puro (`calcular_contactable`, `CONFIANZA_CANAL`, `es_contacto_nominal`);
- dos adaptadores de `Enriquecedor`: `sitio_web` (robots, SSRF por salto, 2 MB, 3 redirecciones) y `croma_rues_co` (por nombre, filtro local por ciudad, match único por NIT, matrícula activa);
- el adaptador `JevClasificador` detrás de un puerto `ClasificadorEncaje`, con payload por clave, enum cerrado y datos delimitados;
- los casos de uso `EnriquecerLead` y `ClasificarEncajeICP`, con costos `croma_consulta`, `web_fetch` y `jev_tokens` por lead (`fuente=NULL`, `lote_id=NULL`);
- `sin_enriquecer()` y `guardar_enriquecimiento()` en `RepositorioLeads`;
- el comando `uv run python -m app.cli enriquecer --tenant --busqueda`;
- la migración 0008, que es una propuesta: columnas de enriquecimiento y de contacto cifrado en `leads`, la vista nueva `v_leads_icp` y cuatro columnas al final de `v_tablero_fuentes`;
- la guarda de catálogo restringida a `BASE TABLE`;
- el tablero con `con_telefono · contactables` y el % no contactable;
- el eval `encaje_icp` apuntando a `jev`, con el primer baseline fijado con `--motivo`.

## Technical Context

- **Language/Version:** Python 3.12; TypeScript 5.7 con React 18.3.
- **Primary Dependencies:** httpx, pyyaml, SQLAlchemy Core + psycopg 3, todas ya en `main`. **No hay dependencias nuevas.** `ipaddress`, `urllib.robotparser` y `re` son de la stdlib. `jev-code` es un binario externo (D10) que se invoca por subprocess o HTTP según cómo lo exponga TypeSafe (P8).
- **Storage:** Postgres. Una migración a mano, la **0008**, PENDIENTE DE APROBACIÓN DE DANIEL.
- **Testing:**
  - pytest con `httpx.MockTransport` y un DNS falso inyectable para el SSRF;
  - `JevFalso` para los tests unitarios y de contrato;
  - integración contra Postgres real como `app_rt`;
  - Vitest + MSW en el front.
- **Constraints:**
  - la spec pide ≤ 4 h;
  - Croma comparte 100 req/24h y 1.500 créditos/mes con la 002 y la 003 (`fuentes.yaml` `limites.croma`);
  - ningún HTTP corre dentro de una transacción abierta (pooler en modo transacción, mismo criterio que la 005);
  - la red real solo se usa en la corrida avisada del eval (Fase 9).
- **Scale/Scope:** 1 módulo nuevo, 3 adaptadores, 2 casos de uso, 1 puerto nuevo + 2 métodos en uno existente, 9 columnas, 1 vista nueva, 1 vista reemplazada y 1 subcomando de CLI.

## Dependencias externas

Estado verificado con `git show origin/main:<ruta>` y `rg` sobre **550928d**, mirando el árbol y no los planes de los otros slices.

| ID | Qué necesita la 006 | De qué slice | ¿En `main`? | Evidencia | Qué bloquea |
|---|---|---|---|---|---|
| D1 | Puerto `RepositorioLeads` y tabla `leads` con `tipo_titular` | 002/003 | ✅ Sí | `descubrimiento/dominio/puertos.py`; 0002 y 0003 | Nada: se extiende |
| D2 | `RegistroCostos` y `costos.tipo` con `web_fetch`, `jev_tokens`, `croma_consulta` | 002 | ✅ Sí | `costos/dominio/puertos.py`; CHECK de 0002 | Nada: no hace falta tocar el CHECK de `tipo` ni sumar columnas (P9) |
| D3 | `Cifrador` y `catalogo_sensibles` | 003 | ⚠ Parcial | `seguridad/cifrado.py`. El catálogo solo tiene `nombre`/`direccion` | Fase 6. Se resuelve si se aprueba P3 (la 0008 suma `telefono`/`email` al catálogo) |
| D4 | Columnas de contacto cifradas, `telefono_canal` / `email_canal` y el tipo `CanalPublicado` | 003 | ❌ No | `leads` en `main` no tiene ninguna; el `Lead` del dominio tampoco | Fases 6, 7 y 8. Se resuelve si se aprueba P3 |
| D5 | `nombre_normalizado` y `web_canal` (`normalizar_dominio`) | 003 | ❌ No | `leads` tiene `web`, pero no `web_canal` ni `nombre_normalizado` | Fase 4 por nombre. Fase 6 usa `web` mientras tanto |
| D6 | `v_leads_icp` y columna `icp` en `v_tablero_fuentes` | 005 | ❌ No | 0006 crea `v_tablero_fuentes(fuente, encontrados, unicos)` y `v_atribuciones`, sin `icp` ni `v_leads_icp`. `test_toda_vista_es_security_invoker` **sí** está (`tests/…/test_rls.py:160`) | Fases 6 y 7. Se resuelve si se aprueba P2 |
| D7 | Transporte/adaptador Croma y su limitador (`requests_24h`, `creditos_mes`, `LimiteFuenteAgotado`) | 002 | ⚠ Parcial | El limitador está. **No hay adaptador ni transporte Croma** | Fase 4 (el transporte lo escribe la 006) |
| D8 | Eval `encaje_icp`: dataset etiquetado, `evals.yaml`, `fingerprint.py`, `baseline.json`, `JuezClaude` y `run.py` real | 004 | ⚠ Parcial | Están el puerto `Juez`, `JuezFalso` y los scorers de forma. `run.py` es un stub que devuelve 99. No hay `evals.yaml`, dataset, baseline ni fingerprint | Fase 9 |
| D9 | API `GET /tablero/fuentes` real y `test_api_busquedas.py` | 005 | ⚠ Parcial | El front de la 005 está en `main` (#37) y en Vercel (#39), con `icp` en `tipos.ts`. `api/tablero.py` y `api/busquedas.py` siguen en 501. No hay `test_api_busquedas.py` | Fase 8 |
| D10 | Acceso a `jev-code` / TypeSafe con `TYPESAFE_DEFAULT_MODEL=jev-1.13.0` | externo | — | Credencial y binario, no código | Fase 9 (corrida real). Las Fases 5 y 6 corren con `JevFalso` (P8) |
| D11 | `croma_rues_co` con búsqueda por **nombre** | config | ❌ Conflicto | `fuentes.yaml` dice `endpoint: /co/rues/entity-by-nit/v1` (por NIT) | Con P1: la vía por NIT queda libre; la vía por nombre espera a D5 y a un endpoint por nombre |

**Qué fases quedan desbloqueadas:**
- **Hoy, sin esperar a nadie:** Fase 1 (puerta y esqueletos), Fase 2 (dominio puro, con `CanalPublicado` propio de la 006 si se aprueba P3), Fase 3 (`sitio_web`) y Fase 5 (`JevClasificador` con `JevFalso`).
- **Si Daniel aprueba P1–P3 y el DDL de la 0008:** Fase 4 por la vía del NIT, Fase 6 y Fase 7. La vía por nombre de la Fase 4 sigue esperando a D5.
- **Siguen bloqueadas:** Fase 8 (D9, la API real del tablero) y Fase 9 (D8 y D10).

## Constitution Check

| Principio | Qué entrega | Estado |
|---|---|---|
| I Hexagonal | `enriquecimiento/dominio` sin `httpx` ni `infraestructura`, con contrato en import-linter y canario. Adaptadores registrados en `fuentes.yaml`. Puertos `Enriquecedor` y `ClasificadorEncaje` con contrato parametrizado. | ✅ |
| II Test primero | Cada verde tiene antes un rojo por aserción y su mutación (ver `tasks.md`). Los esqueletos van primero. El advisor revisa antes de aceptar. | ✅ |
| III Tenant/RLS | Sin tablas nuevas: `leads` ya tiene RLS. `v_leads_icp` se crea y `v_tablero_fuentes` se reemplaza, las dos con `security_invoker`; `test_toda_vista_es_security_invoker` (`test_rls.py:160`, en `main`) lo vigila. `guardar_enriquecimiento` corre como `app_rt` con `SET LOCAL app.tenant_id`. | ✅ |
| IV Migraciones | Una migración a mano, la 0008, con el DDL **PENDIENTE DE APROBACIÓN DE DANIEL**. `app/modelos.py` suma las 8 columnas de `leads` y la de `busquedas` y el drift sigue vacío. | ⚠ pendiente |
| V Seguridad | SSRF validado antes de **cada** salto. robots.txt, tope de 2 MB por stream, timeout corto. Lo extraído no va al log. Credencial de jev por `Settings`, nunca en el repo. Datos del lead delimitados en el payload de jev (inyección de prompt). | ✅ (security revisa) |
| VI Contacto | Email y teléfono nuevos se cifran con el mismo `Cifrador` y catálogo de la 003 (D3/D4). Las vistas exponen solo la etiqueta (`telefono_canal IS NOT NULL`), nunca el dato. La guarda de catálogo pasa a `BASE TABLE` sin aflojar el caso `leads.telefono` en claro. | ⚠ depende de D4 |
| VII Cumplimiento | `contactable` exige `juridica` + canal publicado. `desconocido` se trata como natural. El contacto nominal se descarta. No se borra ningún lead `no_encaja` ni natural. | ✅ (advisor revisa) |
| VIII Costos | Cada operación registra antes de devolver o de lanzar, con `lead_id` set y `fuente`/`lote_id` NULL. Nunca entra a `v_prorrateo`. | ✅ (advisor revisa) |
| IX Evals | `encaje_icp` con `jev-1.13.0` fijo. Primer baseline con `--motivo` obligatorio por fingerprint nuevo. k=1 solo si `determinacion == 1.0` a k=3. El umbral no baja. | ⚠ depende de D8 |
| X Doc viva | `docs/arquitectura-backend.md` suma el módulo `enriquecimiento`. `docs/decisiones.md` suma la 0008 y el criterio de `BASE TABLE`. | ✅ |

## Lo que se usa sin redefinir

| Qué | Dónde está fijado |
|---|---|
| `RegistroCostos.registrar`, `requests_24h`, `creditos_mes` | `backend/app/modulos/costos/dominio/puertos.py` (main) |
| Tipos de costo `croma_consulta`, `web_fetch`, `jev_tokens` | CHECK de `costos.tipo` en `0002_descubrimiento.sql` (main) |
| Tarifas `croma.usd_por_credito`, `web_fetch_usd`, `jev.in_usd_por_M` | `backend/config/tarifas.yaml` (main), leídas como `Decimal(str(…))` igual que `cli.py:_cargar_tarifas` |
| `Cifrador.cifrar/descifrar(columna, valor, tenant_id, lead_id)` | `backend/app/seguridad/cifrado.py` (main) |
| CHECKs de `leads`: juridica en claro, no-juridica cifrado | 0003 y 0005 (main) |
| `LimiteFuenteAgotado` | `descubrimiento/dominio/errores.py` (main) |
| Límites de Croma | `fuentes.yaml` `limites.croma` (main) |
| Puerto `Juez`, `Veredicto`, `SalidaJuezInvalida` | `backend/evals/jueces/puerto.py` (main) |
| `CanalPublicado`, jerarquía de canal | 003 (**D4, no en main**; si se aprueba P3 los define la 006) |
| `normalizar_dominio`, `nombre_normalizado` | 003 (**D5, no en main**) |
| `test_toda_vista_es_security_invoker` | `backend/tests/integration/test_rls.py:160` (main) |
| `v_tablero_fuentes(fuente, encontrados, unicos)`, `v_atribuciones` | `0006_libro_costos_busqueda.sql` (main) |
| `v_leads_icp`, `icp` | 005 (**D6, no en main**; si se aprueba P2 los crea la 006) |
| `fingerprint.py`, `evals.yaml`, `baseline.json`, `dataset.json` | 004 (**D8, no en main**) |

## Cambios de puerto

```python
# enriquecimiento/dominio/puertos.py
@dataclass(frozen=True)
class ContactoPublicado:
    emails: tuple[str, ...]
    telefonos: tuple[tuple[str, CanalPublicado], ...]   # (valor, canal); el valor nunca sale de memoria sin cifrar
    estado: Literal["ok", "sin_sitio", "fetch_bloqueado_por_robots", "truncado", "fallo"]

@dataclass(frozen=True)
class VerificacionTitular:
    tipo_titular: Literal["juridica", "desconocido"]
    motivo: Literal["match_unico", "sin_match", "ambiguo", "matricula_inactiva"]   # va al log de la corrida, no al lead

class EnriquecedorContacto(Protocol):        # sitio_web
    def enriquecer(self, lead_id: UUID, dominio: str) -> ContactoPublicado: ...

class VerificadorTitular(Protocol):          # croma_rues_co
    def verificar(self, lead_id: UUID, nombre_normalizado: str, ciudad: str | None) -> VerificacionTitular: ...

@dataclass(frozen=True)
class Encaje:
    etiqueta: Literal["encaja", "no_encaja", "ninguna"]
    probabilidad: float

class ClasificadorEncaje(Protocol):          # jev
    def clasificar(self, lead_id: UUID, descripcion_icp: str, nombre: str, ciudad: str | None, actividad: str | None) -> Encaje: ...

# descubrimiento/dominio/puertos.py — RepositorioLeads suma:
    def sin_enriquecer(self, busqueda_id: UUID) -> list[LeadParaEnriquecer]: ...
    def guardar_enriquecimiento(self, lead_id: UUID, r: ResultadoEnriquecimiento) -> None: ...
```

Son dos puertos y no un `Enriquecedor` genérico porque los dos adaptadores reciben entradas distintas (dominio vs nombre + ciudad) y devuelven cosas distintas. Un Protocol común obligaría a un `dict` sin tipo.

## Diseño por área

**Dominio (puro).**
- `calcular_contactable(tipo_titular, telefono_canal, email_canal, es_nominal)` devuelve `(bool, razon | None)` con la precedencia `persona_natural`, después `sin_canal_publicado`, después `contacto_nominal`.
- `CONFIANZA_CANAL`: `whatsapp_comercial > sitio_web > osm_contacto > whatsapp_osm`.
- `elegir_canal(actual, nuevo)` solo reemplaza si el nuevo tiene más confianza.
- `es_contacto_nominal` usa `^[a-z]+\.[a-z]+@` sin distinguir mayúsculas.

**`sitio_web`.**
- Resolvedor DNS inyectable. Rechaza si **cualquier** IP resuelta es privada, loopback, link-local o reservada. Valida antes de robots.txt y antes de cada salto.
- `follow_redirects=False` con un loop manual de hasta 3 saltos; el 4.º lanza `DemasiadasRedirecciones`.
- Lee el stream por chunks y corta en 2 MB.
- Extrae `mailto:`, `wa.me/` y teléfonos con regex. `wa.me` entra como `whatsapp_comercial` y gana sobre el teléfono plano.
- Registra `web_fetch` solo por request real, robots incluido (P9). El corte por SSRF no hace request y no registra costo; no hay fila con costo 0 ni columna nueva en `costos`.

**`croma_rues_co`.**
- Busca por `nombre_normalizado`, filtra por ciudad en local y agrupa por NIT.
- Un solo NIT con matrícula activa da `juridica`. Cualquier otro caso da `desconocido` con un motivo.
- Antes del request consulta `requests_24h`/`creditos_mes` contra `limites.croma` y lanza `LimiteFuenteAgotado` sin request.
- Registra `croma_consulta` antes de devolver.
- **Bloqueado por D11/P1:** el endpoint configurado es por NIT.

**`JevClasificador`.**
- Payload `{"actividad_declarada", "nombre_negocio", "ciudad", "descripcion_icp"}`. Los valores del lead van dentro de un bloque delimitado y escapado.
- Salida validada con un enum cerrado y probabilidad en `[0,1]`. Si no cumple, lanza `SalidaJevInvalida`, **después** de registrar `jev_tokens`.
- `encaje_jev_v1.json` vive junto al adaptador (contrato `app ↛ evals`).

**Casos de uso.**
- `EnriquecerLead` recorre `sin_enriquecer(busqueda)`. Por lead: verifica el titular si es `desconocido`, después `sitio_web` si hay `web_canal`, después la jerarquía y el nominal, después `contactable`.
- `ClasificarEncajeICP` corre después y usa el mismo `guardar_enriquecimiento`.
- Ningún HTTP corre dentro de la transacción: primero se junta todo en memoria y después una sola UPDATE por lead.
- `LimiteFuenteAgotado` corta la corrida. Los leads ya guardados quedan.

**`guardar_enriquecimiento` (punto de security).** Si el titular sube de `desconocido` a `juridica`, los CHECKs de 0003/0005 obligan a mover `nombre` y `direccion` de cifrado a claro **en la misma UPDATE**: se descifra `nombre_cifrado`/`direccion_cifrada` y se pone NULL en las cifradas. Es un cambio de exposición de datos (P7). Email y teléfono se guardan siempre cifrados, sea cual sea el titular.

**CLI.** `enriquecer --tenant --busqueda` compone los adaptadores igual que `descubrir` en `cli.py` e imprime el resumen (subieron a juridica, contactables, `no_encaja`). Nunca imprime contacto.

**Front.** `Tablero.tsx` suma `con_telefono · contactables` y el % `no_contactables_politica / icp` con un decimal entero ("14 %"). Muestra "sin dato" con `icp=0`. El front formatea y no cuenta.

## Migración 0008 — PENDIENTE DE APROBACIÓN DE DANIEL

> **PENDIENTE DE APROBACIÓN DE DANIEL.** Esto es una propuesta dentro del plan. No se crea `supabase/migrations/0008_enriquecimiento.sql` hasta que Daniel apruebe este DDL. La spec dice `0005`. En `main` están 0001, 0002, 0003, 0005 y 0006, y la **0007 queda reservada para la 012**. Si al momento de T001 hay otra migración mergeada, se usa el siguiente número libre.

- `costos.tipo` **no cambia**: su CHECK ya admite las tres operaciones (D2). P9 no suma columnas a `costos`.
- Las columnas de contacto y `v_leads_icp` entran acá porque Daniel aprobó P3 y P2.
- `con_telefono` cuenta la **etiqueta** `telefono_canal`, nunca el dato.
- Igual que la 0006, sin `BEGIN`/`COMMIT` propios.

```sql
-- 0008_enriquecimiento.sql — PENDIENTE DE APROBACIÓN DE DANIEL

-- encaje y contactable viven en leads: son uno por lead, igual que tipo_titular.
ALTER TABLE public.leads
  ADD COLUMN contactable          boolean     NOT NULL DEFAULT false,
  ADD COLUMN razon_no_contactable text        NULL,
  ADD COLUMN encaje               text        NULL,
  ADD COLUMN enriquecido_en       timestamptz NULL,
  -- P3 (decidido): contacto cifrado como nombre/direccion en la 0003. La app cifra (AES-GCM); SQL no.
  ADD COLUMN telefono_cifrado     bytea       NULL,
  ADD COLUMN email_cifrado        bytea       NULL,
  ADD COLUMN telefono_canal       text        NULL,
  ADD COLUMN email_canal          text        NULL;

ALTER TABLE public.leads
  ADD CONSTRAINT leads_razon_no_contactable_enum
    CHECK (razon_no_contactable IN ('persona_natural','sin_canal_publicado','contacto_nominal')),
  -- contactable nunca lleva razón.
  ADD CONSTRAINT leads_contactable_sin_razon
    CHECK (NOT contactable OR razon_no_contactable IS NULL),
  -- Sin enriquecer se permite "false sin razón" (los defaults sobre filas existentes);
  -- enriquecido, o es contactable o tiene razón. La igualdad estricta rompería el ALTER (23514).
  ADD CONSTRAINT leads_enriquecido_con_veredicto
    CHECK (enriquecido_en IS NULL OR contactable OR razon_no_contactable IS NOT NULL),
  ADD CONSTRAINT leads_encaje_enum
    CHECK (encaje IN ('encaja','no_encaja','ninguna')),
  -- Mismo criterio que la 0003: nonce de 12 + etiqueta GCM de 16; un bytea más corto no es un cifrado.
  ADD CONSTRAINT leads_telefono_cifrado_ck
    CHECK (telefono_cifrado IS NULL OR octet_length(telefono_cifrado) > 28),
  ADD CONSTRAINT leads_email_cifrado_ck
    CHECK (email_cifrado IS NULL OR octet_length(email_cifrado) > 28),
  ADD CONSTRAINT leads_canal_enum
    CHECK (telefono_canal IN ('whatsapp_comercial','sitio_web','osm_contacto','whatsapp_osm')
       AND email_canal    IN ('whatsapp_comercial','sitio_web','osm_contacto','whatsapp_osm')),
  -- La etiqueta sin dato (o el dato sin etiqueta) es un estado roto.
  ADD CONSTRAINT leads_canal_con_dato
    CHECK ((telefono_canal IS NULL) = (telefono_cifrado IS NULL)
       AND (email_canal    IS NULL) = (email_cifrado    IS NULL));

-- P5 (decidido): la descripción del ICP vive en la búsqueda.
ALTER TABLE public.busquedas ADD COLUMN descripcion_icp text NULL;

-- sin_enriquecer() filtra por esto en cada corrida.
CREATE INDEX leads_sin_enriquecer ON public.leads (tenant_id) WHERE enriquecido_en IS NULL;

-- P2 (decidido): v_leads_icp la crea la 006. Una fila por aparición del lead en una fuente.
-- encaje IS NULL (sin enriquecer) sigue entrando: la 006 solo resta lo que jev marcó no_encaja.
CREATE VIEW public.v_leads_icp WITH (security_invoker = true) AS
  SELECT lf.fuente, lf.lead_id, lf.busqueda_id
  FROM public.lead_fuentes lf
  JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
  WHERE l.encaje IS DISTINCT FROM 'no_encaja';

-- v_tablero_fuentes: el SELECT de la 0006 tal cual (fuente, encontrados, unicos, fila TOTAL y HAVING)
-- y las columnas nuevas AL FINAL: CREATE OR REPLACE no deja reordenar, renombrar ni cambiar tipos.
-- El LEFT JOIN es 1:1 (cada lead_fuentes tiene un lead), así que count(*) no cambia.
-- icp y los contadores cuentan leads distintos del ICP (encaje distinto de no_encaja).
-- no_contactables_politica excluye sin_canal_publicado: no es política, es falta de canal.
-- Repetir security_invoker: si se omite, el REPLACE lo pierde.
CREATE OR REPLACE VIEW public.v_tablero_fuentes WITH (security_invoker = true) AS
  SELECT lf.fuente,
         count(*)                   AS encontrados,
         count(DISTINCT lf.lead_id) AS unicos,
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja')                       AS icp,
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.telefono_canal IS NOT NULL)                                 AS con_telefono,
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja' AND l.contactable)      AS contactables,
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.razon_no_contactable IN ('persona_natural','contacto_nominal')) AS no_contactables_politica
  FROM public.lead_fuentes lf
  LEFT JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
  GROUP BY lf.fuente
  UNION ALL
  SELECT 'TOTAL',
         count(*),
         count(DISTINCT lf.lead_id),
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'),
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja' AND l.telefono_canal IS NOT NULL),
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja' AND l.contactable),
         count(DISTINCT lf.lead_id) FILTER (WHERE l.encaje IS DISTINCT FROM 'no_encaja'
                                              AND l.razon_no_contactable IN ('persona_natural','contacto_nominal'))
  FROM public.lead_fuentes lf
  LEFT JOIN public.leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
  HAVING count(*) > 0;

-- v_atribuciones (0006) no cambia.

-- Los GRANT/REVOKE de la 0006 sobreviven al REPLACE; la vista nueva necesita los suyos.
-- Mismo bloque que la 0006: solo si existen los roles de Supabase (en vanilla no hay nada que revocar).
GRANT SELECT ON public.v_leads_icp, public.v_tablero_fuentes TO app_rt;
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON public.v_leads_icp, public.v_tablero_fuentes FROM anon, authenticated;
  END IF;
END
$$;
```

`catalogo_sensibles` (`seguridad/cifrado.py`) suma `telefono` y `email` a `CIFRADAS` en el mismo PR (P3). No es DDL: es código de la app.

Si Daniel aprueba, entra también `backend/tests/arquitectura/test_migracion_0008.py` con el patrón de `test_migracion_0006.py`: el archivo contiene los CHECKs, repite `security_invoker` en cada vista, no toca `costos` y no reordena las columnas de `v_tablero_fuentes`.

## Fases y dueños

| Fase | Qué | Dueño | Bloqueada por | Parada |
|---|---|---|---|---|
| 1 | Puerta, esqueletos, contrato import-linter | lead | — | Daniel aprueba la 0008 antes de la Fase 6 |
| 2 | Dominio puro | lead | — (`CanalPublicado` propio si se aprueba P3) | advisor: tests de cumplimiento |
| 3 | `sitio_web` | lead | — | **security**: SSRF, robots, 2 MB, redirecciones, logs |
| 4 | `croma_rues_co` | lead | P1 (vía NIT); D5 y D11 (vía nombre) | advisor: costos y limitador |
| 5 | `JevClasificador` + contrato | lead | — (con `JevFalso`) | **security**: inyección de prompt. advisor: costos |
| 6 | Migración 0008 (columnas) + repo + `EnriquecerLead` | lead | P2, P3 + aprobación del DDL (D5 solo para `web_canal`; mientras, `web`) | **advisor + security**: `guardar_enriquecimiento` (paso a claro, cifrado) |
| 7 | Vistas + guarda `BASE TABLE` | lead | P2 + aprobación del DDL | **security**: guarda de catálogo. advisor: fixture A–J |
| 8 | API y front del tablero | lead | D9 | advisor |
| 9 | Eval `encaje_icp` con jev | lead + Daniel | D8, D10 | Daniel autoriza la corrida real con costo estimado |
| 10 | Cierre: docs, suite, lista de commits | lead + swarm | — | advisor: diff final; Daniel: push |

## Validación (quickstart)

```bash
# Offline, sin red ni base:
uv run pytest -q tests/unit/enriquecimiento tests/contratos/test_clasificador_encaje.py
uv run lint-imports

# Con Postgres de prueba (desde cualquier worktree):
scripts/test-backend.sh tests/integration/test_enriquecimiento.py tests/integration/test_vistas_tablero.py

# Corrida manual contra una búsqueda real (Croma y sitios reales: se avisa antes):
uv run python -m app.cli enriquecer --tenant <id> --busqueda <id>

# Eval (Fase 9, con D8 y D10, avisada con costo estimado):
uv run python -m evals.run --tenant <id> --eval encaje_icp --actualizar-baseline \
  --motivo "primer baseline real con jev, reemplaza al juez Claude provisional de la 004"
```

## Project Structure

```text
backend/app/modulos/enriquecimiento/
├── dominio/{contactable.py, canal.py, puertos.py, errores.py}
├── aplicacion/{enriquecer_lead.py, clasificar_encaje.py}
└── infraestructura/adaptadores/{sitio_web.py, croma_rues.py, jev_clasificador.py, encaje_jev_v1.json}
backend/app/modulos/descubrimiento/dominio/puertos.py          # +sin_enriquecer, +guardar_enriquecimiento
backend/app/modulos/descubrimiento/infraestructura/…repo…      # implementación Postgres
backend/app/cli.py                                             # +enriquecer
backend/app/modelos.py                                         # +8 columnas en leads, +1 en busquedas
backend/config/fuentes.yaml                                    # sitio_web y croma_rues_co a catálogo (P1, P4)
backend/tests/unit/enriquecimiento/{test_contactable, test_sitio_web, test_croma_rues, test_jev_classify}.py
backend/tests/contratos/test_clasificador_encaje.py
backend/tests/integration/{test_enriquecimiento, test_vistas_tablero}.py
backend/tests/arquitectura/{test_costos_por_adaptador, test_import_linter, test_migracion_0008}.py
backend/evals/evals.yaml                                       # encaje_icp → jev (D8)
frontend/src/tablero/{Tablero.tsx, Tablero.test.tsx, tipos.ts}
supabase/migrations/0008_enriquecimiento.sql                   # SOLO después de la aprobación de Daniel
```

## Complexity Tracking

| Qué | Por qué no lo más simple | Alternativa descartada |
|---|---|---|
| Dos puertos (`EnriquecedorContacto`, `VerificadorTitular`) en vez de un `Enriquecedor` | Entradas y salidas distintas; un puerto común sería `dict → dict` | Un Protocol genérico con `trae: list[str]` |
| Loop manual de redirecciones | `follow_redirects=True` no deja validar SSRF en cada salto | Validar solo la URL inicial (se esquiva con un 302 a `localhost`) |
| `CHECK` de dos condiciones en vez de `contactable = (razon IS NULL)` | La igualdad estricta rompe el `ALTER` sobre filas existentes (23514) | Un estado `pendiente` en `razon_no_contactable` |

## Preguntas de producto abiertas

Cada una dice qué bloquea. Daniel las decidió el 2026-10-17 ("sí a todo", con P6 y P9 precisadas); la columna "Decisión" es la versión final. Los "Ojo" marcan dónde la decisión toca el árbol actual. El DDL de la 0008 sigue PENDIENTE DE APROBACIÓN DE DANIEL (T005).

| # | Pregunta | Bloquea | Decisión (Daniel, 2026-10-17) |
|---|---|---|---|
| P1 | `fuentes.yaml` configura `croma_rues_co` con `/co/rues/entity-by-nit/v1` (búsqueda por NIT). La spec busca por `nombre_normalizado` porque los leads de OSM no traen NIT. ¿Croma expone un endpoint de RUES por nombre? ¿Se cambia el endpoint, o el adaptador solo verifica leads que ya tienen NIT? | Fase 4 | Por NIT cuando el lead lo tiene; por nombre si no. La vía por nombre espera a D5 y a confirmar que Croma tiene un endpoint de RUES por nombre. |
| P2 | `v_leads_icp` y la columna `icp` son de la 005 y no están en `main`. ¿La 006 espera a que lleguen, o crea `v_leads_icp` ella misma (y entonces con qué definición de ICP)? | Fases 6 y 7 | `v_leads_icp` la crea la 006, en la 0008 (ver DDL). ICP = lead cuyo `encaje` no es `no_encaja`. |
| P3 | Las columnas de contacto cifradas, `telefono_canal`/`email_canal` y `CanalPublicado` son de la 003 y no están en `main`. ¿Se espera a la 003, o la 006 las agrega en la 0008? | Fases 2, 6, 7 y 8 | Las columnas de contacto las agrega la 006 en la 0008, cifradas como en la 0003 (`bytea`, AES-GCM en la app, CHECK de `octet_length > 28`). |
| P4 | `croma_supersociedades_detalle_co` está `habilitado: true` en `fuentes.yaml`, y la spec dice que sigue OFF y fuera de alcance. ¿Cuál vale? | Fase 1 (config) | `croma_supersociedades_detalle_co` apagado (`habilitado: false`) en T001. |
| P5 | ¿Dónde vive la descripción del ICP que recibe `jev_classify`? `busquedas` tiene solo `criterios jsonb`. ¿Es una clave dentro de `criterios`, una columna nueva o algo que escribe el operador en el front? | Fase 5 (caso de uso) | La descripción del ICP vive en `busquedas`: columna `descripcion_icp text NULL` en la 0008. |
| P6 | El baseline de `encaje_icp` de la 004 no existe en `main` (no hay dataset etiquetado ni `baseline.json`). ¿La 006 espera al baseline del juez Claude, o fija directamente el primero con jev, y contra qué piso se compara entonces? | Fase 9 | El piso es el `umbral` 0.70 (no el `corte` 0.5, que es la probabilidad a partir de la cual se cuenta `encaja`). **Ojo:** `evals.yaml` todavía no existe en `main` (D8). |
| P7 | Subir un lead de `desconocido` a `juridica` obliga, por los CHECKs de 0003/0005, a guardar `nombre` y `direccion` en claro. Es una decisión de privacidad: ¿se acepta el paso a claro automático por un match único de RUES, o se requiere otra señal? | Fase 6 | Sí, en claro al confirmarse jurídica, con registro en `cumplimiento`. **Ojo:** `cumplimiento` tiene `UNIQUE(lead_id)` y el descubrimiento ya inserta la fila de cada lead (`repositorio_leads.py:21`): es un UPDATE de esa fila en la misma transacción, no una fila nueva. |
| P8 | ¿Cómo se invoca `jev-code` en producción (Railway): binario en la imagen, servicio HTTP de TypeSafe, o solo local? ¿Qué credencial usa y quién la carga? | Fase 9 y despliegue | `JevFalso` hasta que Daniel defina el acceso real. Fase 9 sigue bloqueada por D10. |
| P9 | ¿Se registra un `web_fetch` cuando el SSRF o robots.txt cortan el fetch del sitio? robots.txt es un request real; el corte por SSRF no hace ningún request. | Fase 3 (costos) | Solo se registra costo cuando hay request real, robots.txt incluido. El corte por SSRF no registra nada. Sin columna nueva en `costos`. |
| P10 | ¿`sitio_web` corre también para leads `natural`/`desconocido`? No los vuelve contactables, pero gasta un request y guarda contacto cifrado de una persona natural. | Fase 6 | No: `sitio_web` corre solo para jurídicas (también las que suben a jurídica en la misma corrida). |
| P11 | Si no alcanza el tiempo, la spec propone cortar en el orden `sitio_web`, después `croma_rues_co`, después `jev` y `contactable` sobre lo que haya. ¿Se mantiene ese orden para la demo, dado que D4–D6 tampoco están? | Orden de corte | Sí, se mantiene el orden de corte. |
