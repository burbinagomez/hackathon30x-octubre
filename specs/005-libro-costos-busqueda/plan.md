# Implementation Plan: 005 — Libro de costos, CPL por fuente y "Nueva búsqueda"

**Branch**: `feature/005-libro-costos-busqueda` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Este plan no rediseña lo que fijan la 002, la 003 y la 011: lo cita por línea. Las referencias son a los planes en sus ramas, todavía no en `main`:
> - **002 plan** = `git show 89d3e59:specs/002-puertos-registro-supersociedades/plan.md`;
> - **003 plan** = `git show f393852:specs/003-osm-dedup/plan.md`;
> - **011 plan** = `git show c64c5f8:specs/011-datos-gov-co/plan.md`;
> - **011 spec** = `git show c64c5f8:specs/011-datos-gov-co/spec.md`. c64c5f8 es el commit de la 011 que aprobó el advisor, con la D7 aplicada. Las líneas citadas son las mismas que en 6c4bd7d y f8f9456.
> - **002 migración** = `git show 561f6c4:supabase/migrations/0002_descubrimiento.sql`.
>
> Lo que la 005 necesita y ninguna de esas fija va a **Preguntas abiertas**, con la sección exacta y un default propuesto, que no se aplica hasta que lo apruebe el dueño.
>
> Artefactos: como en la 002 y la 011, este slice entrega solo `plan.md` y `tasks.md`. Lo que irían en research, data-model, contracts y quickstart está resumido acá.

## Summary

La 005 entrega:
- las vistas SQL del libro de costos (`security_invoker`), con el fixture de 10 leads calculado a mano;
- `lote_id = busquedas.id`;
- `contar()` en `FuenteDescubrimiento`, con suite de contrato propia;
- `costo_maximo_llamada` en `MetaFuente` y el tope de gasto a valor de lista;
- `gasto_busqueda` en `RegistroCostos`;
- el post-filtro de palabras clave y exclusiones;
- los casos de uso `VistaPrevia` y `EjecutarBusqueda` con tope;
- auth mínima con **Supabase Auth**: la API verifica el access token (JWKS), resuelve el tenant en `usuarios` por `sub` con una función `SECURITY DEFINER`, y la RLS sigue con `app.tenant_id`;
- los endpoints HTTP;
- el front con login, "Nueva búsqueda" y tablero, con límites por feature e i18n es/en;
- el E2E local;
- la cola de revisión de dedup, que es recortable.

Además absorbe de la 011, por la D7, seis tests y el verde del tablero de naturales (T049 de la 011).

## Technical Context

- **Language/Version:** Python 3.12; TypeScript 5.7 con React 18.3.
- **Primary Dependencies, back:** FastAPI, SQLAlchemy Core + psycopg 3, httpx y pyyaml, todos de la 002. Nueva: **`pyjwt[crypto]`** (verificar el token con JWKS; `cryptography` para ES256/RS256).
- **Primary Dependencies, front:** react-i18next e i18next como dependencias nuevas. Como devDependencies nuevas: `eslint`, `typescript-eslint`, `eslint-plugin-boundaries`, `eslint-plugin-import`, `eslint-import-resolver-typescript` y `eslint-plugin-i18next`. MSW 2.6.6 ya está en `package.json`.
- **Storage:** Postgres (`postgres:16` en CI) y una migración a mano. El número se discute en la pregunta P5.
- **Testing:** pytest, con integración contra Postgres real como `app_rt`. Vitest + Testing Library + MSW en el front y Playwright para el E2E local. Se usan `httpx.MockTransport` y un reloj inyectable, como en la 002 y la 003.
- **Constraints:**
  - ≤ 5 h, con el mínimo de demo declarado en la spec;
  - Croma da ~100 requests en 24 h y 1.500 créditos al mes: hay una sola corrida real, avisada (Fase 12);
  - el pooler va en modo transacción: ningún HTTP corre dentro de una transacción abierta (002 plan:286 y OQ1).
- **Scale/Scope:** 2 módulos nuevos (`tablero`, `acceso`), 9 vistas, 1 tabla, 2 funciones, ~11 endpoints y 4 features de front.

## Constitution Check

| Principio | Qué entrega | Estado |
|---|---|---|
| I Hexagonal | `contar` y `costo_maximo_llamada` entran al puerto con contrato parametrizado sobre el catálogo. `tablero` y `acceso` respetan el `layers` de import-linter (002). En el front, `eslint-plugin-boundaries` con canario (`limites.test.ts`). | ✅ |
| II Test primero | Cada test tiene una mutación que lo pone en rojo por aserción (ver `tasks.md`). Los esqueletos van antes del rojo, para que no haya `ImportError` ni `AttributeError`. El advisor y security revisan antes de aceptar. | ✅ |
| III Tenant/RLS | Vistas `security_invoker` con `test_rls[vista]` y control positivo. `usuarios` con RLS y sin privilegios para `app_rt`. Las funciones `SECURITY DEFINER` llevan `search_path` y `REVOKE` a `PUBLIC`/`anon`/`authenticated`. `pg_views` entra en `test_privilegios_supabase`. | ✅ |
| IV Migraciones | Una migración a mano. `app/modelos.py` suma columnas y `usuarios`, y el drift sigue vacío (las vistas no las compara `compare_metadata`; T006 lo confirma). | ✅ |
| V Seguridad | `AUTH_JWKS_URL` y `AUTH_ISSUER` (públicos, sin secreto de firma en la api), `WEB_ORIGIN` y `CROMA_BASE_URL` por `Settings`. Docs desactivadas, CORS cerrado, token fuera de logs y `extra='forbid'`. **Enmienda pendiente** del dueño: la web necesita la publishable key de Supabase (constitución:30, ver Conflictos). | ⚠ pendiente |
| VI Contacto | El formulario no pide contacto y la cola no lo expone (`test_cola_no_expone_contacto`). El email del operador vive en `auth.users` (Supabase) y `usuarios` no lo guarda: minimización total (reemplaza al `email_hmac` de P13). | ✅ |
| VII Cumplimiento | Una empresa filtrada por palabra clave no genera lead ni `cumplimiento`. Fusionar no toca `cumplimiento`. `v_atribuciones` sale de `lead_fuentes`. | ✅ |
| VIII Costos | `contar` registra antes de devolver o de lanzar, igual que `buscar`. Todo descubrimiento lleva `lote_id = busqueda.id`. El CPL sale solo de vistas sobre `costos`. | ✅ |
| IX Evals | N/A (sin IA). `fuente='evals'` aparte, en `v_costo_evals`. | — |
| X Doc viva | `docs/arquitectura-backend.md` y `-frontend.md`, más la corrección de PRD §4, en la Fase 13. | ✅ |

## Lo que se usa sin redefinir

| Qué | Dónde está fijado |
|---|---|
| `CriteriosICP.filtros` | 002 plan:58 |
| `PaginaEmpresas.total` ("lo usa la vista previa del 005") | 002 plan:77; `truncado` y `descartados_sin_nombre` en 003 plan:62 |
| `MetaFuente`, armada desde el YAML | 002 plan:80-89; `cuenta_naturales` con default `False` en 011 plan D2 (c64c5f8:74) |
| `FuenteDescubrimiento` con `meta` como atributo + `buscar` | 002 plan:91-93; D1 de la 011 |
| `CriterioNoSoportado`, `LimiteFuenteAgotado`, `FuenteNoDisponible` | 002 plan:97-99 |
| `RepositorioLeads` | 002 plan:108-115; métodos de dedup en 003 plan:64 |
| `OperacionCosto`, `RegistroCostos` (`registrar`, `requests_24h`, `creditos_mes`) | 002 plan:122-138; módulo `costos` en 002 plan:297 |
| Raíz de composición, tarifas `Decimal(str(v))`, adaptadores por búsqueda con `lote_id` | 002 plan:150 y :286 |
| `costos.ts` lo pone la base | 002 plan:209 y :291 |
| `costos.tipo` cerrado (ya trae `croma_consulta`, `overpass_query` y `socrata_descarga`) | 002 plan:210; la 005 no lo toca |
| `fuente_cache` global, no expuesta | 002 plan:201 |
| `seleccionar_fuentes` → `(seleccionadas, ignoradas)` | 003 plan:65; motivos en 003 spec:41-45 |
| `EjecutarBusqueda` captura errores por fuente | 002 plan:295, 003 plan:55 |
| Costo por intento de `overpass_query`, espera no cobrada, timeout de cliente de 30 s | 003 plan:40, 003 spec:211 y :299 |
| Fórmula de `costo_maximo_llamada` de datos.gov.co | 011 spec (c64c5f8):230 |
| Discriminador de caché de datos.gov.co (`tipo: filas\|naturales`, sin `contar`) | 011 (advisor de la 011); la 005 suma `contar` |
| `busquedas.naturales_por_fuente` | 011 spec (c64c5f8):37 y :203 |

## Cambios de puerto (son enmienda: la spec 005 es la spec que pide 002 plan:103)

```python
# descubrimiento/dominio — solo se agrega
class FuenteDescubrimiento(Protocol):
    meta: MetaFuente
    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas: ...   # sin cambios
    def contar(self, criterios: CriteriosICP) -> int | None: ...                      # nuevo

@dataclass(frozen=True)
class MetaFuente:                     # 002 plan:80, + un campo con default
    ...
    costo_maximo_llamada: Decimal = Decimal("0")   # origen: ver P4; el contrato exige > 0

class FabricaFuentes(Protocol):       # nuevo; implementación en app/api (raíz de composición)
    def __call__(self, lote_id: UUID) -> Mapping[str, FuenteDescubrimiento]: ...

# costos/dominio
class RegistroCostos(Protocol):
    ...
    def gasto_busqueda(self, busqueda_id: UUID) -> Decimal: ...   # Σ unidades × costo_unitario, gratis incluido (P3)
```

`contar` tiene el mismo contrato que `buscar`:
- valida contra `meta.filtros` antes de hacer cualquier request;
- deja una fila en `costos` por intento, antes de devolver o de lanzar;
- lanza los mismos errores.

`None` significa que la fuente no da conteo, con `motivo='sin_conteo'`.

El default `Decimal("0")` de `costo_maximo_llamada` no puede dejar entrar gratis al tope a un adaptador nuevo, como `croma_dian_trade_co` (spec:27). Para eso la suite de contrato suma `test_costo_maximo_llamada_positivo[…]`, que exige `type is Decimal and > 0`.

`gasto_busqueda` de un lote sin filas devuelve `Decimal("0")`, nunca `None` (`COALESCE`): `None + Decimal` rompe el tope.

## Diseño por área (resumen de la spec, con lo que agrega el plan)

**Vistas** (spec:313-335):
- Las 9 vistas van en un archivo de migración, en este orden de dependencia: `v_costos` → `v_costo_evals`, `v_leads_icp` → `v_prorrateo` → `v_desperdicio`, `v_costo_por_lead` → `v_costo_por_canal` → `v_tablero_fuentes` → `v_atribuciones`.
- Todas llevan `WITH (security_invoker = true)` y `GRANT SELECT … TO app_rt`.
- Ninguna redondea.
- Los tests comparan `Decimal` con `Decimal` construido desde string y además asertan `type(v) is Decimal`. Así un cast a `float8` da rojo aunque el valor coincida (`2.0 == Decimal(2)` es `True`). Los esperados del fixture no son enteros (0.3375, 0.2375, 0.282…), y eso cierra la misma puerta por segunda vía.

**`costo_maximo_llamada` por adaptador** (spec:350-353):
- **cs:** 1 crédito × `usd_por_credito`;
- **OSM:** 2 × 30 s × `computo_seg_usd`;
- **`datos_gov_co_rues`:** 2 requests × 2 intentos × 30 s × `computo_seg_usd`, según la 011 spec (c64c5f8):230.

Cada uno tiene su test en el archivo del adaptador, y `test_costo_maximo_suma_costo_maximo_llamada_de_cada_fuente` lleva un caso con las tres fuentes.

**Caché de `contar` en datos.gov.co:** la 011 deja su discriminador en `tipo: filas|naturales`, y la 005 suma `tipo: contar`. La segunda llamada con los mismos criterios no hace request ni escribe costo (`test_contar_segunda_llamada_sale_del_cache`). En cs no hace falta un discriminador: `contar` y `buscar(1)` comparten clave a propósito (P12).

**Lote = búsqueda:** `VistaPrevia` crea el borrador **antes** de construir los adaptadores, y los pide con `fabrica_fuentes(borrador.id)` (002 plan:286). `EjecutarBusqueda` los vuelve a pedir con el mismo id. La 002 entrega instancias ya armadas desde la raíz de composición (002 plan:150), pero acá el `lote_id` nace dentro del caso de uso. Sin el puerto `FabricaFuentes`, `aplicacion/` tendría que importar el catálogo concreto. El Protocol vive en `descubrimiento/dominio/`, la implementación en `app/api` (cierra sobre catálogo, tarifas, transportes y `RegistroCostos`) y los tests de caso de uso usan una falsa.

**Tope:** el chequeo es `gasto_busqueda(id) + meta.costo_maximo_llamada ≤ tope` antes de cada `buscar`. Lo hace el caso de uso, no el adaptador: el adaptador no conoce el tope.

**Auth (Supabase Auth, decisión del dueño 2026-10-18):** ver la sección "Auth con Supabase Auth" abajo y spec:365-383. Reemplaza al login propio (scrypt, JWT HS256, `email_hmac`, `usuario_para_login`, `SESSION_SECRET`, `EMAIL_HMAC_CLAVE`).

**Tablero:**
- `repositorio_tablero.py` solo lee vistas. Suma la columna de naturales de la 011 desde `busquedas.naturales_por_fuente`, con `DISTINCT ON (fuente) … ORDER BY fuente, creado_en DESC`. `busquedas.creado_en` ya existe (002 migración:19); la 011 spec:203 lo escribe `creada_en`, pero es la misma columna. También la combina en la API con `meta.cuenta_naturales` del registro.
- La cobertura por país sale del registro, no de la base.

**Front:** spec:414-474, sin cambios. Hoy el repo tiene `src/setupTests.ts`; la spec pide `src/test/setup.ts` y `servidor.ts`, así que T034 lo mueve.

## Migración

Va un único archivo, `supabase/migrations/NNNN_libro_costos_busqueda.sql` (el número sale de P5), con la tabla de spec:398-410:
- en `busquedas`: `+ costo_estimado_usd`, `+ costo_maximo_usd`, `+ ejecutada_en` y el `CHECK` nuevo de `estado` (P1);
- en `leads`: `+ fusionado_en uuid NULL` con `FOREIGN KEY (tenant_id, fusionado_en) REFERENCES leads (tenant_id, id)`, que se apoya en `leads_tenant_id_id_key` (002 migración:41) y sigue el patrón de las FKs compuestas de la 002 (002 migración:57). Una FK simple no pasa por RLS: el tenant B podría apuntar a un lead de A (`test_tenant_b_no_fusiona_con_lead_de_a`);
- en `revision_dedup`: `+ motivo`;
- la tabla `usuarios` (`auth_user_id uuid PRIMARY KEY`, `tenant_id`, `idioma`, `creado_en`; sin email ni clave) con RLS;
- las funciones `tenant_de_usuario(p_auth_user_id uuid)` (MIN) y `fijar_idioma` (Pulido);
- los índices `(tenant_id, lote_id)` y `(busqueda_id, fuente)`;
- las 9 vistas;
- un `DO` con el guard de `pg_roles` para los `REVOKE EXECUTE`.

`app/modelos.py` suma las columnas y `usuarios`.

### DDL de la 0004 v2 (APROBADO 2026-10-18)

Es el contenido exacto de `supabase/migrations/0006_libro_costos_busqueda.sql`. Basado en el v1 (que queda abajo como superseded): mismo `CHECK` de estados, vistas y `REVOKE`; cambia `usuarios` (`auth_user_id`, sin FK) y la función de acceso `tenant_de_usuario(uuid)`, y suma el `REVOKE` global de `EXECUTE` a `PUBLIC` en funciones nuevas. El dueño lo aprobó tal cual (2026-10-18, con security OK). `backend/tests/arquitectura/test_migracion_0006.py` compara el archivo con este bloque byte a byte.

```sql
-- 0004: libro de costos y búsqueda [MIN]. SQL a mano. Corre como postgres (dueño). Va después de la 0003.
-- Login con Supabase Auth (decisión del dueño, 2026-10-18): usuarios no guarda email ni clave; el email vive en auth.users.

-- P1 (dueño, 2026-10-18): unión de los 8 estados. Un solo ALTER: nunca queda la tabla sin CHECK.
ALTER TABLE public.busquedas
  DROP CONSTRAINT busquedas_estado_check,
  ADD CONSTRAINT busquedas_estado_check CHECK (estado IN (
    'creada', 'terminada', 'con_errores',
    'borrador', 'ejecutando', 'completada', 'tope_alcanzado', 'error'));

-- auth_user_id = auth.users.id = claim `sub` del access token de Supabase. Sin email ni clave: viven en auth.users.
-- Sin FK a auth.users: en CI y local (postgres vanilla) el esquema auth no existe, y una FK condicional haría que
-- prod y CI tengan esquemas distintos que el drift check no ve. La autoridad es esta fila: si no hay fila, no hay acceso.
CREATE TABLE public.usuarios (
  auth_user_id uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES public.tenants(id),
  idioma       text CHECK (idioma IN ('es', 'en')),
  creado_en    timestamptz NOT NULL DEFAULT now()
);

-- RLS sin FORCE a propósito: app_rt no es dueño y la política lo alcanza; el dueño (postgres) es quien
-- corre tenant_de_usuario antes de conocer el tenant. Con FORCE, esa función fallaría o dependería de BYPASSRLS.
-- app_rt no tiene ningún privilegio sobre la tabla: entra solo por la función.
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_aislado ON public.usuarios
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

-- Resolver el tenant: después de verificar el token, antes de conocer el tenant. Devuelve la fila de ESE
-- auth_user_id y nada más (PRIMARY KEY: 0 o 1 fila). El tenant NO sale del token (user_metadata lo edita el usuario).
-- Todo calificado con public.; pg_catalog va implícito primero, pg_temp al final.
CREATE FUNCTION public.tenant_de_usuario(p_auth_user_id uuid)
  RETURNS TABLE (tenant_id uuid, idioma_usuario text, idioma_tenant text)
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
  SELECT u.tenant_id, u.idioma, t.idioma
  FROM public.usuarios u
  JOIN public.tenants t ON t.id = u.tenant_id
  WHERE u.auth_user_id = p_auth_user_id
$$;
REVOKE ALL ON FUNCTION public.tenant_de_usuario(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.tenant_de_usuario(uuid) TO app_rt;

-- Vistas [MIN]. security_invoker: corren como app_rt y pasan por la RLS de lead_fuentes.
-- Pulido: un CREATE OR REPLACE VIEW sin WITH (security_invoker = true) BORRA la opción; repetirla siempre.
CREATE VIEW public.v_tablero_fuentes WITH (security_invoker = true) AS
  SELECT fuente, count(*) AS encontrados, count(DISTINCT lead_id) AS unicos
  FROM public.lead_fuentes
  GROUP BY fuente
  UNION ALL
  SELECT 'TOTAL', count(*), count(DISTINCT lead_id)
  FROM public.lead_fuentes
  HAVING count(*) > 0;

CREATE VIEW public.v_atribuciones WITH (security_invoker = true) AS
  SELECT a.fuente, a.texto, a.url, a.orden
  FROM (VALUES
    ('osm_overpass', '© OpenStreetMap contributors', 'https://www.openstreetmap.org/copyright', 1),
    ('datos_gov_co_rues', 'Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)',
     'https://creativecommons.org/licenses/by-sa/4.0/', 2)
  ) AS a(fuente, texto, url, orden)
  WHERE EXISTS (SELECT 1 FROM public.lead_fuentes lf WHERE lf.fuente = a.fuente);

GRANT SELECT ON public.v_tablero_fuentes, public.v_atribuciones TO app_rt;

-- El EXECUTE a PUBLIC de las funciones nuevas es un default GLOBAL de Postgres: un ALTER DEFAULT PRIVILEGES
-- ... IN SCHEMA no lo puede sacar, y anon/authenticated lo heredan por PUBLIC. Se cierra para todo lo que cree postgres.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- Roles de Supabase. Supabase da EXECUTE en funciones nuevas de public a anon/authenticated por default
-- privileges; la 0002 solo cerró TABLES y SEQUENCES. Solo si existen (en vanilla no hay nada que revocar).
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON FUNCTION public.tenant_de_usuario(uuid) FROM anon, authenticated;
    REVOKE ALL ON public.usuarios, public.v_tablero_fuentes, public.v_atribuciones FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
  END IF;
END
$$;
```

### DDL de la 0004 (APROBADO 2026-10-18; SUPERSEDIDO por el login con Supabase Auth, no se usa)

Es el contenido exacto de `supabase/migrations/0006_libro_costos_busqueda.sql` ([MIN]); `backend/tests/arquitectura/test_migracion_0006.py` compara el archivo con este bloque. Va entre la 0003 y la 0005.

```sql
-- 0004: libro de costos y búsqueda [MIN]. SQL a mano. Corre como postgres (dueño). Va después de la 0003.

-- P1 (dueño, 2026-10-18): unión de los 8 estados. Un solo ALTER: nunca queda la tabla sin CHECK.
ALTER TABLE public.busquedas
  DROP CONSTRAINT busquedas_estado_check,
  ADD CONSTRAINT busquedas_estado_check CHECK (estado IN (
    'creada', 'terminada', 'con_errores',
    'borrador', 'ejecutando', 'completada', 'tope_alcanzado', 'error'));

-- P13 (dueño): sin email. email_hmac = HMAC-SHA256(EMAIL_HMAC_CLAVE, lower(strip(email))): 32 bytes.
-- El CHECK de largo impide guardar el email crudo en bytea por error.
CREATE TABLE public.usuarios (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES public.tenants(id),
  email_hmac bytea NOT NULL CHECK (octet_length(email_hmac) = 32),
  hash_clave text NOT NULL,
  idioma     text CHECK (idioma IN ('es', 'en')),
  creado_en  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT usuarios_email_hmac_key UNIQUE (email_hmac)
);

-- RLS sin FORCE a propósito: app_rt no es dueño y la política lo alcanza; el dueño (postgres) es quien
-- corre usuario_para_login antes de conocer el tenant. Con FORCE, esa función fallaría o dependería de BYPASSRLS.
-- app_rt no tiene ningún privilegio sobre la tabla: entra solo por la función.
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_aislado ON public.usuarios
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

-- Login: antes del tenant. Devuelve la fila de ESE email_hmac y nada más (UNIQUE: 0 o 1 fila).
-- Todo calificado con public.; pg_catalog va implícito primero, pg_temp al final.
CREATE FUNCTION public.usuario_para_login(p_email_hmac bytea)
  RETURNS TABLE (id uuid, tenant_id uuid, hash_clave text, idioma_usuario text, idioma_tenant text)
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
  SELECT u.id, u.tenant_id, u.hash_clave, u.idioma, t.idioma
  FROM public.usuarios u
  JOIN public.tenants t ON t.id = u.tenant_id
  WHERE u.email_hmac = p_email_hmac
$$;
REVOKE ALL ON FUNCTION public.usuario_para_login(bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.usuario_para_login(bytea) TO app_rt;

-- Vistas [MIN]. security_invoker: corren como app_rt y pasan por la RLS de lead_fuentes.
-- Pulido: un CREATE OR REPLACE VIEW sin WITH (security_invoker = true) BORRA la opción; repetirla siempre.
CREATE VIEW public.v_tablero_fuentes WITH (security_invoker = true) AS
  SELECT fuente, count(*) AS encontrados, count(DISTINCT lead_id) AS unicos
  FROM public.lead_fuentes
  GROUP BY fuente
  UNION ALL
  SELECT 'TOTAL', count(*), count(DISTINCT lead_id)
  FROM public.lead_fuentes
  HAVING count(*) > 0;

CREATE VIEW public.v_atribuciones WITH (security_invoker = true) AS
  SELECT a.fuente, a.texto, a.url, a.orden
  FROM (VALUES
    ('osm_overpass', '© OpenStreetMap contributors', 'https://www.openstreetmap.org/copyright', 1),
    ('datos_gov_co_rues', 'Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)',
     'https://creativecommons.org/licenses/by-sa/4.0/', 2)
  ) AS a(fuente, texto, url, orden)
  WHERE EXISTS (SELECT 1 FROM public.lead_fuentes lf WHERE lf.fuente = a.fuente);

GRANT SELECT ON public.v_tablero_fuentes, public.v_atribuciones TO app_rt;

-- Roles de Supabase. Supabase da EXECUTE en funciones nuevas de public a anon/authenticated por default
-- privileges; la 0002 solo cerró TABLES y SEQUENCES. Solo si existen (en vanilla no hay nada que revocar).
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON FUNCTION public.usuario_para_login(bytea) FROM anon, authenticated;
    REVOKE ALL ON public.usuarios, public.v_tablero_fuentes, public.v_atribuciones FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
  END IF;
END
$$;
```

## Auth con Supabase Auth (decisión del dueño, 2026-10-18)

**Flujo.** El front inicia sesión con `supabase-js` (P15: email + contraseña). Manda el access token como `Authorization: Bearer`. La API:
1. verifica el token (firma, `exp`, `iss`, `aud`) con las claves públicas del proyecto;
2. toma `sub` y llama `tenant_de_usuario(sub)`: 0 filas → 403 (`sin_acceso`);
3. abre la unidad de trabajo con `SET LOCAL app.tenant_id` (002). La RLS no cambia.

**Verificación (lo más simple y seguro).**
- `PyJWKClient(AUTH_JWKS_URL)` con caché, `algorithms=["ES256", "RS256"]` (nunca HS256: evita la confusión de algoritmo con la clave pública), `audience="authenticated"`, `issuer=AUTH_ISSUER` y `options={"require": ["exp", "sub", "aud", "iss"]}`.
- La api no tiene ningún secreto de firma ni `service_role`. `AUTH_JWKS_URL` y `AUTH_ISSUER` son URLs públicas y **no** empiezan por `SUPABASE_`, así que `verificar_entorno` (config.py:87-89) no cambia.
- Alternativa descartada: el secreto JWT compartido (HS256). Pondría en el entorno de la api una clave que acuña tokens de cualquier usuario, y `verificar_entorno` ya prohíbe credenciales de Supabase ahí.
- JWKS inaccesible: falla cerrado (503), nunca 200.
- Los tests no usan red: generan un par EC P-256 y le inyectan al verificador un JWKS local.

**El tenant sale de `usuarios`, nunca del token.** `user_metadata` lo edita el propio usuario y `app_metadata` depende de cómo se configure el proyecto; ningún claim de tenant se lee. Revocar es borrar la fila de `usuarios`: la función devuelve 0 filas y el token deja de servir aunque no haya vencido (1 h).

**`tenant_de_usuario(uuid)` frente a lectura directa.** Con lectura directa, la política `tenant_id = current_setting('app.tenant_id')` falla antes de conocer el tenant. Habría que sumar una segunda política por `auth_user_id` y darle `SELECT` a `app_rt` sobre la tabla. Se queda la función: `app_rt` sigue sin ningún privilegio sobre `usuarios` y el único patrón de acceso es "dame el tenant de ESTE uid" (mismo patrón que aprobó security para `usuario_para_login`).

**Qué desaparece:** `POST /auth/sesion`, `email_hmac`, `hash_clave`, `usuario_para_login`, `EMAIL_HMAC_CLAVE`, `SESSION_SECRET`, `hmac_email`, scrypt y el JWT propio. **Qué queda:** PyJWT (con `[crypto]`), solo para verificar. `GET /usuarios/me` devuelve `idioma_usuario` e `idioma_tenant` para `elegirIdioma`; `PATCH /usuarios/me` (Pulido) llama a `fijar_idioma(sub, idioma)`.

**Alta de usuarios (paso humano, frontera de Daniel).** El dueño crea el usuario en el panel de Supabase. Después `backend/scripts/crear_usuario.py --auth-user-id UUID --tenant UUID [--idioma es|en]`, con la URL de `postgres` por `getpass`, inserta la fila de `usuarios`.

**Riesgo aceptado.** El rate limit y el bloqueo por intentos del login pasan a ser los de Supabase Auth, no los de la api (la 012 ya no los construye).

**Variables.** api: `AUTH_JWKS_URL`, `AUTH_ISSUER`, `CORS_ORIGINS` (**divergencia con T030, decisión de coordinación 2026-10-18:** se mantiene `CORS_ORIGINS`, que ya existe en `.env.example` y tiene tests; `WEB_ORIGIN` no se crea. Orígenes permitidos, métodos GET/POST, headers `Authorization` y `Content-Type`, sin `allow_credentials`). web: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` (clave pública por diseño; choca con constitución:30, abajo).

### Conflictos con la constitución y CLAUDE.md (enmienda que decide el dueño; no se editan acá)

| Dónde | Dice | Conflicto |
|---|---|---|
| `CLAUDE.md:23` | "Postgres en Supabase (solo Postgres: sin Auth, Storage, Edge Functions ni Data API sobre `public`)" | Pasa a usar Auth. Storage, Edge Functions y Data API siguen apagados. |
| `.specify/memory/constitution.md:30` (V) | "Ninguna key de Supabase (anon, service_role, publishable, secret) existe en el entorno de `api` ni de `web`: la app no arranca si la ve." | `supabase-js` en el front necesita `VITE_SUPABASE_URL` y la publishable key. Enmienda mínima: la publishable key se permite **solo en `web`**; `service_role`, secret y todo lo de Supabase en `api` siguen prohibidos. |
| `.specify/memory/constitution.md:3` | Cabecera con las versiones (1.2.0 "Postgres en Supabase") | La enmienda cambia un principio (V) y el alcance de Supabase: es MAJOR, versión 2.0.0. |
| `.specify/memory/constitution.md:22` (III) | "`anon` y `authenticated` no tienen privilegios sobre tablas de `public`" | Sigue valiendo: la api entra como `app_rt`, nunca con el rol del token. No es conflicto, pero Auth hace que `authenticated` exista de verdad: `test_privilegios_supabase` pasa a ser más importante. |
| `.specify/memory/constitution.md:34` (VI) | "correos… se cifran en reposo" | Sin conflicto: el email del operador no está en nuestra base. |
| `backend/app/config.py:10-11, 87-89` y `backend/tests/arquitectura/test_secrets.py:38-39` | `verificar_entorno` corta si ve `SUPABASE_*`, `sb_publishable_` o un JWT con rol `anon`/`service_role` en el entorno de `api` | Sin cambio **si** la api usa `AUTH_JWKS_URL` y `AUTH_ISSUER`. Si el dueño prefiere `SUPABASE_URL` en la api, hay que cambiar esa guarda. |
| `specs/001-walking-skeleton/spec.md:10, 28-29`, `plan.md:13`, `quickstart.md:46-48` | Mismo texto de "solo Postgres" y la guarda de keys | Se alinean con la enmienda. |

## Validación (quickstart)

```bash
cd backend && uv sync && uv run pytest -q && uv run lint-imports
scripts/migrar_local.sh postgresql://postgres@localhost:5432/postgres
cd frontend && npm ci && npm test && npx playwright test
```

La corrida real (Fase 12) se avisa antes. Se anota el saldo de Croma antes y después, si viene `total` y cuánto tarda la ejecución.

## Project Structure

```text
backend/
├── pyproject.toml                         # + pyjwt[crypto]
├── config/{tarifas.yaml (+ limites_app.tope_maximo_usd), actividades.yaml (+ nombre_es/nombre_en)}
├── app/
│   ├── config.py                          # + auth_jwks_url, auth_issuer, web_origin, croma_base_url
│   ├── main.py                            # docs off, CORS, routers
│   ├── modelos.py
│   ├── api/{sesion.py, busquedas.py, tablero.py, dedup.py, actividades.py, usuarios.py}
│   └── modulos/
│       ├── costos/{dominio/puertos.py (+gasto_busqueda), infraestructura/postgres_costos.py}
│       ├── descubrimiento/
│       │   ├── dominio/{modelos.py (+costo_maximo_llamada), puertos.py (+contar), palabras_clave.py}
│       │   ├── aplicacion/{vista_previa.py, ejecutar_busqueda.py (+tope), resolver_revision.py}
│       │   └── infraestructura/adaptadores/{croma_supersociedades.py, osm_overpass.py, datos_gov_co_rues.py}
│       ├── tablero/infraestructura/persistencia/repositorio_tablero.py
│       └── acceso/{dominio/{puertos.py (VerificadorToken), errores.py}, infraestructura/{verificador_jwks.py, persistencia/repositorio_usuarios.py}}
├── scripts/crear_usuario.py               # inserta la fila de usuarios (auth_user_id + tenant); el usuario de Supabase lo crea el dueño
└── tests/
    ├── contratos/test_fuente_descubrimiento.py      # + 3 de contar
    ├── unit/descubrimiento/{test_croma_supersociedades, test_osm_overpass, test_datos_gov_co,
    │                        test_seleccion_fuentes, test_palabras_clave, test_vista_previa, test_ejecutar_con_tope}.py
    ├── integration/{test_vistas_costos, test_rls, test_privilegios_supabase, test_usuarios_repo,
    │                test_costos_repo, test_auth, test_api_busquedas, test_revision_dedup}.py
    └── stubs/servidor_fuentes.py
supabase/migrations/NNNN_libro_costos_busqueda.sql
frontend/
├── eslint.config.js
├── vitest.config.ts
├── src/{App.tsx, main.tsx, api/cliente.ts, i18n/{index.ts, es.json, en.json, elegirIdioma.ts},
│        compartido/{SelectorIdioma.tsx, formato.ts}, test/{setup.ts, servidor.ts},
│        acceso/, busqueda/, tablero/, dedup/}
├── tests/arquitectura/{limites.test.ts, i18n.test.ts}
└── e2e/busqueda.spec.ts
docs/{arquitectura-backend.md, arquitectura-frontend.md, prd.md (§4)}
```

## Preguntas abiertas

Ninguna se resuelve en este plan. Cada fila dice qué tareas bloquea.

**Decisiones del dueño (2026-10-18):**
- **P1 aprobada con el default:** el `CHECK` de `busquedas.estado` es la unión de los 8 valores; la CLI sigue igual; en la API una fuente caída con otra que respondió deja `completada` con el error por fuente, y `error` es solo cuando fallan todas.
- **P2 aprobada con el default:** `crear_borrador`, `fijar_estimados`, `obtener_borrador` y `pasar_a_ejecutando`; los métodos del 002 no cambian.
- **P4 aprobada con el default:** la fábrica de cada adaptador calcula `costo_maximo_llamada` con la tarifa resuelta; el YAML no lo declara.
- **T001 sin la 004:** la 004 (evals) no es requisito para arrancar la 005; `v_costo_evals` lee una tabla vacía hasta que la 004 escriba.
- **P5:** la migración de la 005 es la `0004`; la `0003` queda para el cifrado de `nombre`/`direccion` de la 003.
  _Reemplazado 2026-10-18: el archivo pasa a `0006_libro_costos_busqueda.sql` sin cambiar una línea de SQL, porque la `0005` de la 003 ya estaba aplicada en prod y `supabase db push` no inserta una versión anterior a la última remota. El texto "0004" del DDL de abajo es el aprobado y no se toca._
- **Puerta T001: nada la bloquea.** P1 (estados) quedó aprobada arriba.
- **P13 queda sin efecto:** el dueño decidió login con Supabase Auth (2026-10-18); `email_hmac` desaparece. Preguntas nuevas: P15 a P18.
- **P1, P2 y P4** están aprobadas con el default (arriba); no queda ninguna pendiente de aprobación.
- P3, P5, P7–P12 y P14 no bloquean.
- P6 se borró: `busquedas.creado_en` ya existe (002 migración:19).

| # | Pregunta (sección exacta) | Bloquea | Default propuesto |
|---|---|---|---|
| P1 | **Estados de `busquedas`.** La 002 fija `CHECK IN ('creada','terminada','con_errores')` (002 plan:208, OQ11 :295). La 005 pide `borrador`/`ejecutando`/`completada`/`tope_alcanzado`/`error` (spec:355). La 011 deja "completada" a la 005 (011 plan D6, c64c5f8:78). Falta definir qué estado deja la CLI y qué es `error` frente a `con_errores` cuando falla una sola fuente. | **Puerta T001.** T008, T024–T027, T032 | El `CHECK` nuevo es la unión de los 8 valores. La CLI sigue igual. En la API, una fuente caída con otra que respondió deja `completada` con el error por fuente en la respuesta, y `error` queda solo para cuando todas fallan. **Efecto a decidir:** si la CLI sigue dejando `terminada`, el tablero de naturales, que toma búsquedas `completada` (011 spec c64c5f8:203), nunca muestra lo que corre la CLI. Eso incluye la demo de conectar y desconectar de la 011. Hay dos salidas: filtrar `estado IN ('completada','terminada')`, o que la CLI deje `completada`. El dueño elige, y queda explícito en T032. |
| P2 | **`RepositorioLeads` no crea borradores.** `crear_busqueda(criterios)` (002 plan:109) no recibe canal, tope, mensaje ni costos estimados, y no hay transición `borrador → ejecutando`. | T024–T027 | Se agregan `crear_borrador(criterios, canal, tope, mensaje) -> UUID`, `fijar_estimados(id, estimado, maximo)`, `obtener_borrador(id)` y `pasar_a_ejecutando(id) -> bool` (`UPDATE … WHERE estado='borrador'`). Los métodos del 002 no cambian. |
| P3 | **`gasto_busqueda` en el Protocol `RegistroCostos`** (002 plan:135-138). Si entra al Protocol, los registros falsos de la 002 y la 003 tienen que implementarlo. | T014–T015, T024 | Entra al Protocol, y el registro falso compartido suma el método en el mismo commit. |
| P4 | **De dónde sale `costo_maximo_llamada`.** `MetaFuente` "se arma desde la entrada de fuentes.yaml, no desde la clase" (002 plan:80), pero el valor depende de la tarifa (`computo_seg_usd`, `usd_por_credito`) y de constantes del adaptador (timeout, intentos). La 011 lo deja a la 005 (011 plan D2, c64c5f8:74), y la fórmula de datos.gov.co está en la 011 spec (c64c5f8):230. | T016–T020 (falta aprobar el default) | La fábrica de cada adaptador, en `adaptadores/__init__.py`, lo calcula con la tarifa ya resuelta y hace `dataclasses.replace(meta, costo_maximo_llamada=…)`. El YAML no lo declara. |
| P5 | **Número de migración.** La spec dice `0004` (spec:398), y la 011 dice "el siguiente libre… previsiblemente `0004`" (011 plan D8, c64c5f8:80). Con el orden 002 → 003 → 011 → 004 → 005, la 011 toma el `0004` antes. | T001, T005 | El siguiente libre en `main` al pasar la puerta T001 (previsiblemente `0005`). Se corrige `spec.md`. |
| P7 | **`ignorados` por fuente.** `seleccionar_fuentes` devuelve `(seleccionadas: dict[clave, CriteriosICP], ignoradas: dict[clave, motivo])` (003 plan:65), y la vista previa necesita también los criterios ignorados de cada fuente seleccionada (spec:55). | T021, T025 | Se derivan en `VistaPrevia` como `set(criterios.filtros) - set(seleccionadas[k].filtros)`, sin tocar la firma de la 003. **Corregido 2026-10-18 (advisor, T024):** `sorted(set(criterios.filtros) − set(sel[k].filtros) − ({'ciiu'} si 'tipo_negocio' ∈ sel[k].filtros y 'ciiu' ∉ sel[k].filtros))`. El ciiu traducido no es ignorado. Contradice la fórmula anterior; lo fija `test_vista_previa.py::test_ignorados_son_los_criterios_que_la_fuente_no_aplica_y_el_ciiu_traducido_no_cuenta`. El verde debe usar `sorted`. |
| P8 | **Nombre del archivo de selección.** La spec dice `test_seleccion.py` (spec:158) y la 003 crea `test_seleccion_fuentes.py` (003 plan:132). | T021 | Va en `test_seleccion_fuentes.py`, y se corrige `spec.md`. |
| P9 | **`test_tamano_es_refinamiento_no_requisito` puede nacer verde.** La 003 ya manda a `ignorados` los criterios que la fuente no declara (003 spec:45). | T021 | Se acepta como test de caracterización solo si la mutación (tratar `ingresos_min` como requisito) lo pone en rojo, y el advisor lo confirma. |
| P10 | **`EXCLUIDOS`** (002 spec:66, enmendado en 002 plan:297). La 005 suma `repositorio_tablero.py` y `repositorio_usuarios.py` (spec:305). | T033 | Se enmienda en el mismo commit que los crea. |
| P11 | **`limites_app` en `tarifas.yaml`.** Hoy no existe. ¿Lo lee el cargador de tarifas de la 002 o uno aparte? | T032 | Lo lee el mismo cargador, como `Decimal(str(v))`, y llega a la API por `Settings` en la raíz de composición. |
| P12 | **Costo de `contar` de Croma.** Si la página 1 queda en caché, `buscar` no vuelve a cobrar. ¿La fila `croma_consulta` de `contar` es la misma que la de `buscar` (1 crédito en total)? | T017 | Sí: `contar` hace la request y escribe la fila, y `buscar(1)` es cache hit y no escribe nada. Es lo que prueba `test_contar_y_buscar_hacen_una_sola_request`. |
| P13 | ~~Email de `usuarios` (`email_hmac`)~~ | — | **Reemplazada por Supabase Auth (2026-10-18):** el email vive en `auth.users`, `usuarios` no lo guarda. |
| P14 | **Costo de `contar` de OSM en la vista previa de un ICP de BR o PE** (estimado de OSM como cota baja, spec:341). Sin pregunta de diseño, pero se registra para la Fase 12. | — | Se mide en la corrida real. |
| P15 | Método de login con Supabase Auth. | — | **DECIDIDA (dueño, 2026-10-18): email y contraseña.** |
| P16 | ¿FK de `usuarios.auth_user_id` a `auth.users(id)`? | — | **DECIDIDA: sin FK.** Procedimiento de baja: borrar la fila en `usuarios` (T013, T049). |
| P17 | ¿Claves de firma asimétricas (JWKS) en el proyecto Supabase? | T013, T029 | **DECIDIDA: JWKS.** **Pendiente humano (Brayan):** verificar en el panel que el proyecto firma con claves asimétricas y que la Data API no expone `public`. Hasta entonces, la verificación se prueba solo con JWKS local. |
| P18 | Enmiendas a CLAUDE.md y a la constitución. | — | **APROBADA y aplicada** (2026-10-18): `CLAUDE.md:23` y constitución 2.0.0 (V). El chequeo de la enmienda es `frontend/tests/arquitectura/sin_secretos.test.ts` (T039). |
| P19 | **Ciudad sin departamento en CO.** Con `ciudad` y sin `departamento`, `croma_supersociedades_co` queda descartada por `sin_geografia` (su único filtro geográfico es `departamento`), aunque cubra el país. ¿Se deriva el departamento de la ciudad o se hace obligatorio para CO? (Para Daniel; surgió en la revisión de T024.) | — (no bloquea el [MIN]) | Sin default: no se decide ahora. Hoy se descarta con el motivo `sin_geografia`. |

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| Un campo de `MetaFuente` que no sale del YAML (P4) | Depende de la tarifa y del timeout del adaptador, y duplicarlo en el YAML los desincroniza | Declararlo en `fuentes.yaml`: un cambio de tarifa no lo movería |
| Módulo `tablero` sin dominio | La lógica vive en SQL (PRD §7, spec:300) | Calcular el CPL en Python: tendría dos fuentes de verdad |
| Funciones `SECURITY DEFINER` | El login ocurre antes de conocer el tenant, y `app_rt` no puede leer `usuarios` | Darle `SELECT` a `app_rt`: podría volcar los hashes de todos los tenants |
