# Implementation Plan: 012 — Seguridad: cabeceras, CSP, sesión del front, idioma del usuario y límites

**Branch**: `feature/012-seguridad` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

> La spec es anterior a la decisión de Supabase Auth (005 plan:335, constitución 2.0.0). Este plan no la reescribe: marca qué partes quedan superadas ("Qué cambió desde la spec") y planifica lo que sigue valiendo, más cinco entradas nuevas que pidió el dueño (E1–E5). Lo que la spec no decide va a **Preguntas abiertas**, con una propuesta que no se aplica hasta que la apruebe Daniel.
>
> Artefactos: como en la 002, la 005 y la 011, este slice entrega solo `plan.md` y `tasks.md`.

## Summary

La 012 entrega:
- **E1.** CSP y cabeceras de seguridad en `frontend/vercel.json` (el front se publica en Vercel, #39), con `cabeceras.test.ts` sobre ese archivo; el `Caddyfile` queda solo como alternativa;
- **E2.** las fuentes de Google fuera de `index.html` (o permitidas en la CSP, P1), con un test que lo fija;
- **E3.** la sesión de supabase-js fuera de `localStorage` (o la decisión escrita de dejarla, P2);
- **E4.** `PATCH /usuarios/me` con la función `fijar_idioma` (`SECURITY DEFINER`), DDL **pendiente de aprobación de Daniel**;
- **E5.** el rate limit del login: sigue como riesgo aceptado (005 plan:357); la 012 solo deja escrito y verificable qué límite pone Supabase Auth;
- lo de la spec que sigue vigente: revisión `security` de 002–008, PII transversal en logs (middleware de errores y 422 sin `input`), límites por tenant en las rutas que gastan créditos y la pantalla de cumplimiento.

## Technical Context

- **Back:** Python 3.12, FastAPI, SQLAlchemy Core, Postgres con RLS; rol de runtime `app_rt` sin `BYPASSRLS`. Migraciones con Supabase CLI en `supabase/migrations/`.
- **Auth:** Supabase Auth. El front loguea con supabase-js; la api verifica el JWT por JWKS (ES256/RS256, `aud=authenticated`, `iss=AUTH_ISSUER`) y saca el tenant de `tenant_de_usuario(sub)`, nunca del token.
- **Front:** React, Vite, Vitest, Playwright. Sitio estático en Vercel (`www.profitdata.tech`), con `frontend/vercel.json` (hoy solo el rewrite a `/index.html`) y las tres `VITE_*` cargadas en Vercel (`docs/decisiones.md:18`). `frontend/Dockerfile` y `Caddyfile` quedan como alternativa en Railway.
- **Tests:** `scripts/test-backend.sh [ruta]`, `scripts/test-frontend.sh`. Tests de arquitectura del front en `frontend/tests/arquitectura/` (`i18n`, `limites`, `sin_secretos`).

## Constitution Check

- **Principio V (seguridad por PR):** CodeQL (default setup), `required-checks.txt`, gitleaks y `revision-seguridad` ya están en `main` (PR #23, 31b9ce2). La 012 no los rehace; los cita (D2).
- **Principio VI (PII nunca en logs):** el test transversal de la spec sigue vigente (Fase 4).
- **Principio VII (tenant por RLS):** `fijar_idioma` filtra por `tenant_id = current_setting('app.tenant_id')` además de `auth_user_id`; lo prueba `test_fijar_idioma_no_cruza_tenants` con mutación (E4).
- **Migraciones:** el DDL va en este plan marcado **PENDIENTE DE APROBACIÓN DE DANIEL**. No se crea ningún archivo en `supabase/migrations/` hasta esa aprobación (T001, T020).

## Dependencias externas

| Id | Qué | ¿En `main`? | Para qué |
|----|-----|-------------|----------|
| D1 | 005 back: `usuarios`, `tenant_de_usuario`, `ALTER DEFAULT PRIVILEGES … REVOKE EXECUTE` (migración 0006), verificador JWKS | **Sí** (550928d, #40) | E4 copia el patrón de `tenant_de_usuario`; los tests usan sus fixtures (`test_usuarios_repo.py`). |
| D2 | 012 config del repo: CodeQL default setup, `required-checks.txt`, gitleaks, `revision_seguridad.sh`, `veredicto_security.sh`, `verificar_proteccion.sh`, `test_required_checks.py` | **Sí** (PR #23, 31b9ce2) | Paso 2 de la spec: hecho. Queda solo el pendiente humano de `ANTHROPIC_API_KEY`. |
| D3 | 005 back: `GET /usuarios/me` (idiomas del usuario y del tenant), `sesion_actual` | **Sí** (#40, 373c829: `backend/app/api/usuarios.py`, tests en `test_auth.py`). No hay `PATCH`. | `test_fijar_idioma_persiste` lee con el GET; E4 suma el `PATCH` en el mismo router. |
| D4 | 005 front: `SelectorIdioma.tsx` manda `PATCH /usuarios/me {idioma}`, `sesion.ts`, `supabase.ts` | **Sí** (el front ya llama una ruta que no existe y traga el error con `.catch`) | E3 y E4. |
| D5 | 006 enriquecedor: su plan y su migración | **No** (en `main` solo `spec.md`; migraciones 0001–0003, 0005, 0006) | E4 queda fijada en **0007**; la 006 toma la siguiente libre (P4). |
| D6 | 007 (`RUTAS_PUBLICAS`, `/baja/{token}`), 008 (`/calificaciones/importar`), 009 (`/webhooks/whatsapp`) | **No** (`rg` sin rutas en `backend/app`) | Límites por tenant y casos de PII de esas rutas: entran solo las que estén en `main` al arrancar la fase. |
| D7 | Deploy del front en Vercel: `frontend/vercel.json` con el rewrite | **Sí** (#39, eba6e33) | E1 suma `headers` al mismo archivo, sin tocar el rewrite. |

## Qué cambió desde la spec (Supabase Auth)

La spec diseña una sesión propia. Con Supabase Auth esas partes no se construyen; se listan para que no se pierdan en silencio:

| Parte de la spec | Estado | Por qué |
|------------------|--------|---------|
| Qué hace §1: refresh opaco en cookie `HttpOnly`, rotación de un solo uso, tope de 8 h, `SESSION_SECRET` rotable | **Superado** | El refresh lo emite y rota Supabase Auth. La api no firma tokens. |
| `test_refresco.py` entero y los tests de sesión de `test_auth.py` (cookie, `/auth/refrescar`, `/auth/salir`, `Origin`, `sesiones_refresco`, `SESSION_SECRET_ANTERIOR`) | **Superado** | No hay `/auth/sesion` propio: lo fija `test_sin_login_propio.py` (005). |
| Rate limit de `/auth/sesion`, semáforo de scrypt, 429 igual exista o no el email | **Superado → E5** | No hay scrypt ni login en la api. Riesgo aceptado (005 plan:357). |
| `cliente.test.ts`: access en memoria, single-flight del refresh, 409 en curso, restaurar al cargar | **Superado → E3** | El refresh lo hace supabase-js. Lo que queda es dónde guarda la sesión. |
| Proxy same-origin (`/api/*` por la red privada de Railway) | **Sigue, sin urgencia** | Se justificaba por la cookie `SameSite=Strict`. Sin cookie, el proxy solo achica la CSP (`connect-src 'self'` para la api). Con el front en Vercel sería un rewrite de `vercel.json`, no Caddy. Fuera del [MIN]: P5. |
| `test_dockerfile_web_no_recibe_args` (spec:128, :279) | **Superado** | Ya no existe. El vigente es `test_dockerfile_web_solo_recibe_variables_publicas` (`backend/tests/arquitectura/test_secrets.py:87`), que permite exactamente `VITE_API_URL`, `VITE_SUPABASE_URL` y `VITE_SUPABASE_PUBLISHABLE_KEY` (públicas por diseño, 005 plan:359). La 012 no lo toca. Con el front en Vercel, el `Dockerfile` es solo la alternativa; si entra el proxy (P5), `VITE_API_URL` sigue igual y apunta al mismo origen. |
| CSP de la spec con `connect-src 'self'` | **Cambia (E1)** | Bloquearía las llamadas de supabase-js a `VITE_SUPABASE_URL` y las de la api en Railway. `connect-src` suma el origen de Supabase y el de la api. |
| `check_cabeceras.sh` sobre la imagen `web` | **Cambia (E1)** | El front productivo no es la imagen: el test pasa a `cabeceras.test.ts` sobre `vercel.json`. |
| Revisión `security` 002–008, PII transversal, límites por tenant, pantalla de cumplimiento | **Sigue** | No dependen de cómo se loguea. |

La enmienda de la spec, si Daniel aprueba P6, va en un PR aparte y marca lo reemplazado sin borrarlo.

## Diseño por entrada

### E1 — CSP y cabeceras en `frontend/vercel.json`

El front se publica en Vercel (#39, `docs/decisiones.md:18`). Hoy `frontend/vercel.json` solo tiene el rewrite y no pone ninguna cabecera. Se suma un bloque `headers`, sin tocar el rewrite:

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Content-Security-Policy", "value": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://<ref>.supabase.co https://<api-railway>; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" },
        { "key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "no-referrer" },
        { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" },
        { "key": "Cross-Origin-Opener-Policy", "value": "same-origin" }
      ]
    }
  ]
}
```

- `vercel.json` es estático: no lee variables de entorno. Los dos orígenes de `connect-src` van **literales**: el de `VITE_SUPABASE_URL` (`https://<ref>.supabase.co`) y el de `VITE_API_URL` (la api en Railway). Son orígenes públicos, sin path; los dicta Daniel desde las variables de Vercel (T017). Si cambia uno, cambia `vercel.json` en el mismo PR.
- `style-src` y `font-src` quedan en `'self'` solo si E2 se resuelve con self-host (P1).
- Lo que Vercel no hace como Caddy: sacar `Server` (Vercel manda `Server: Vercel`) y cortar el body con 413. El front es estático y no recibe POST; el límite de body y el `Cache-Control: no-store` de las respuestas de la api son de la api en Railway, no de esta entrada.
- **Caddyfile, solo alternativa:** si `web` vuelve a Railway, el mismo juego de cabeceras va en un bloque `header { … -Server }` con `request_body { max_size 1MB }` y los orígenes por `{$SUPABASE_ORIGEN} {$API_ORIGEN}`. No entra en el [MIN] ni lleva test mientras Vercel sea el deploy.

**Test propuesto** (`frontend/tests/arquitectura/cabeceras.test.ts`, junto a `sin_secretos.test.ts`):
- parsea `frontend/vercel.json`; para `source: "/(.*)"` exige la CSP **exacta** (comparada directiva por directiva), HSTS, `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` y COOP;
- `connect-src` trae `'self'`, un origen que matchea `^https://[a-z0-9]+\.supabase\.co$` y el origen de la api; si `VITE_SUPABASE_URL` o `VITE_API_URL` están seteadas en el entorno del test, sus orígenes tienen que estar (el E2E contra el deploy cubre el desfasaje con lo que carga Vercel);
- el rewrite a `/index.html` sigue presente (no se pisa el arreglo de #39).
- **Rojo:** hoy `vercel.json` no tiene `headers` → falla en el primer assert.
- **Mutaciones:** sacar `frame-ancestors 'none'` → rojo; sacar el origen de Supabase de `connect-src` → rojo.
- **E2E** (`frontend/e2e/seguridad.spec.ts::navegar_no_viola_la_csp`): login → tablero → Nueva búsqueda con 0 eventos `securitypolicyviolation`, y la respuesta de `/` trae la CSP. Corre contra el deploy de Vercel en `e2e.yml`, apenas la CSP está arriba.

### E2 — Google Fonts sin CSP en `index.html`

`frontend/index.html` hace `preconnect` a `fonts.googleapis.com` y `fonts.gstatic.com` y carga el CSS de DM Sans y Poppins desde Google. Con la CSP de E1, `style-src 'self'` y `font-src 'self'` lo bloquean: la página carga con la fuente del sistema y el E2E de CSP da rojo.

Dos caminos (fork real, P1):
- **Self-host (propuesta, pendiente de Daniel):** los `.woff2` en `frontend/public/fuentes/` con su `@font-face` en el CSS del proyecto. La CSP no cambia, no hay request a Google (sin IP del usuario a un tercero) y no hay dependencia de red externa en la demo. Costo: bajar los archivos una vez y revisar la licencia (OFL, permite redistribuir).
- **Permitir Google:** `style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com`. Cero archivos nuevos, pero la CSP se abre a un tercero y cada visita le avisa a Google.

**Test propuesto:**
- `frontend/src/test/index_html.test.ts::no_carga_recursos_de_terceros`: lee `index.html` y falla si aparece cualquier `href` o `src` con `https://` (con self-host), o si aparece un origen que no está en la CSP de `vercel.json` (si se permite Google). **Rojo:** hoy encuentra `fonts.googleapis.com`.
- El E2E `navegar_no_viola_la_csp` de E1 lo cubre en el navegador real.
- **Mutación:** volver a pegar el `<link>` de Google → rojo.

### E3 — Sesión de supabase-js en `localStorage`

`frontend/src/api/supabase.ts` llama `createClient(url, key)` sin `auth.storage`: supabase-js guarda access y refresh en `localStorage` (`sb-<ref>-auth-token`). Persiste al cerrar el navegador y lo comparten todas las pestañas.

- **`sessionStorage` (propuesta, pendiente de Daniel):** `createClient(url, key, { auth: { storage: sessionStorage } })`. La sesión muere al cerrar la pestaña y no se comparte entre pestañas.
- **Lo que no cambia:** ante un XSS, `sessionStorage` está tan expuesto como `localStorage`. La mitigación real del robo de token es la CSP de E1; E3 achica la ventana (sesiones olvidadas en una máquina compartida), no el vector.
- **Costo de UX (P2):** abrir un link en otra pestaña pide login de nuevo. Para la demo, una sola pestaña.

**Test propuesto:**
- `frontend/src/api/supabase.test.ts::la_sesion_va_a_sessionStorage`: con `vi.mock("@supabase/supabase-js")` espía (`supabaseFalso.ts` ya exporta `moduloFalso`), importar `supabase.ts` y asertar que el tercer argumento de `createClient` trae `auth.storage === window.sessionStorage`. **Rojo:** hoy el argumento es `undefined`.
- **Mutación:** sacar `storage` → rojo.
- E2E `seguridad.spec.ts::el_token_no_queda_en_localStorage`: después del login, ninguna clave de `localStorage` empieza con `sb-` y termina en `-auth-token`.
- `frontend/src/test/setup.ts:23` ya limpia `sessionStorage` entre tests; no hace falta tocarlo.

### E4 — `PATCH /usuarios/me` con `fijar_idioma` (SECURITY DEFINER)

El front ya manda `PATCH /usuarios/me {idioma}` (`SelectorIdioma.tsx:16`) y la api solo tiene el `GET` (#40): hoy el `PATCH` da 405 y el `.catch` lo traga. `app_rt` no tiene privilegios sobre `usuarios` (0006), así que el UPDATE va por función `SECURITY DEFINER`, con el mismo patrón que `tenant_de_usuario`.

**Ruta:** `PATCH /usuarios/me`, autenticada. Body `IdiomaUsuario(BaseModel, extra="forbid")` con `idioma: Literal["es", "en"]`. El `auth_user_id` sale del `sub` verificado, nunca del body. Llama `fijar_idioma(sub, idioma)` dentro de la transacción con `app.tenant_id` ya seteado. Responde **204**. Si la función cambió 0 filas, 404 (el usuario no es de este tenant).

**DDL — PENDIENTE DE APROBACIÓN DE DANIEL**

Archivo propuesto: `supabase/migrations/0007_fijar_idioma.sql`. Número **fijado en 0007** (en `main` la última es 0006; la 006 toma la siguiente, P4). **No se crea el archivo hasta la aprobación.**

```sql
-- 0007 — fijar_idioma: el usuario cambia su idioma sin que app_rt toque usuarios.
CREATE FUNCTION public.fijar_idioma(p_auth_user_id uuid, p_idioma text)
  RETURNS integer
  LANGUAGE plpgsql VOLATILE SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
DECLARE
  filas integer;
BEGIN
  UPDATE public.usuarios
     SET idioma = p_idioma
   WHERE auth_user_id = p_auth_user_id
     AND tenant_id = current_setting('app.tenant_id')::uuid;
  GET DIAGNOSTICS filas = ROW_COUNT;
  RETURN filas;
END
$$;

REVOKE ALL ON FUNCTION public.fijar_idioma(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.fijar_idioma(uuid, text) TO app_rt;
```

- `p_idioma` inválido lo corta el `CHECK (idioma IN ('es','en'))` de `usuarios`; la ruta lo corta antes con el `Literal` (422).
- `current_setting('app.tenant_id')` sin `missing_ok`: si la api llama sin tenant seteado, la función falla en vez de actualizar sin filtro.
- `RETURNS integer` para que la ruta distinga 1 fila de 0 sin un SELECT extra.
- No toca la RLS de `usuarios`: como `SECURITY DEFINER` corre como `postgres`, que es dueño y la tabla no tiene `FORCE`, la RLS no aplica y el filtro de tenant es el `AND` explícito. Por eso el test de no cruzar tenants lleva mutación.

**Tests** (pedidos por `security`, revisados por él antes de aceptarlos):
- `backend/tests/integration/test_api_usuarios.py::test_fijar_idioma_persiste`: usuario de tenant A con `idioma='es'`; `PATCH /usuarios/me {idioma:'en'}` da 204, y el `GET /usuarios/me` siguiente (D3, ya en `main`) trae `idioma_usuario: 'en'`. **Rojo:** hoy el `PATCH` da 405.
- `::test_fijar_idioma_invalido_da_422[caso]`, con los casos:
  - `pt`, `''`, `EN` (no hay normalización);
  - **mass assignment:** `{idioma:'en', usuario_id:<otro>}`, `{idioma:'en', tenant_id:<B>}`, `{idioma:'en', auth_user_id:<otro>}`;
  cada uno da 422, y después el idioma en la base sigue igual (assert sobre la fila, no solo el status). El 422 no devuelve `input` (cruza con la Fase 4). **Mutación:** sacar `extra="forbid"` → los casos de mass assignment dan 204 → rojo.
- `backend/tests/integration/test_usuarios_repo.py::test_fijar_idioma_no_cruza_tenants`: como `app_rt`, con `app.tenant_id = A`, `fijar_idioma(usuario_de_A, 'en')` devuelve 1; con `app.tenant_id = B`, `fijar_idioma(usuario_de_A, 'es')` devuelve 0 y la fila sigue en `'en'`. **Mutación:** sacar `AND tenant_id = …` → la segunda llamada devuelve 1 → rojo.
- `::test_fijar_idioma_es_security_definer_con_search_path`: parametrizar el test existente `test_tenant_de_usuario_es_security_definer_con_search_path` (`test_usuarios_repo.py:51`) a `[tenant_de_usuario|fijar_idioma]`: `prosecdef` verdadero, `proconfig` con `search_path=public, pg_temp`, sin `EXECUTE` para `PUBLIC`, `anon` ni `authenticated` (cruza con `test_privilegios_supabase.py:98`).
- `::test_fijar_idioma_sin_tenant_seteado_falla`: sin `SET app.tenant_id`, la llamada levanta error y no cambia filas.

### E5 — Rate limit del login

Riesgo aceptado (005 plan:357): no hay login en la api (`test_sin_login_propio.py`), así que el límite y el bloqueo por intentos son los de Supabase Auth. La 012 **no** construye limitador de login.

**Test propuesto:** ninguno en la api; no hay ruta que probar. Lo que se puede dejar:
- una línea en `docs/seguridad/revision-002-008.md` con los valores de rate limit de Auth del proyecto de Supabase (panel → Authentication → Rate Limits), que copia el dueño (paso humano, frontera de Daniel);
- opcional (P3): un check manual, no de CI, que con la Management API lea `rate_limit_*` del proyecto y compare contra un mínimo escrito. Requiere un token de admin que no puede vivir en CI; por eso no es test.

La decisión de si el riesgo sigue aceptado es del dueño (P3).

### Lo que sigue de la spec

- **Revisión `security` de 002–008:** sin cambios. Reporte en `docs/seguridad/revision-002-008.md` (no existe todavía).
- **PII transversal:** sin cambios. `CASOS_PII` suma el caso de `PATCH /usuarios/me`.
- **Límites por tenant:** solo `vista-previa` (30/h) y `ejecutar` (10/h) mientras D6 no esté en `main`. `limites.py` en memoria, con `ponytail:` sobre el proceso único. Sacar los casos de login y scrypt de `test_limites.py`.
- **Pantalla de cumplimiento:** sin cambios; sigue primera en el orden de corte.

## Validación (quickstart)

1. `scripts/test-backend.sh backend/tests/integration/test_api_usuarios.py backend/tests/integration/test_usuarios_repo.py`.
2. `scripts/test-frontend.sh` (incluye `cabeceras.test.ts`, `supabase.test.ts` e `index_html.test.ts`).
3. `curl -sI https://www.profitdata.tech/ | grep -i content-security-policy` después del deploy de Vercel.
4. `e2e.yml` contra el deploy: `seguridad.spec.ts`.

## Project Structure

```
frontend/vercel.json                                 E1 (headers)
frontend/tests/arquitectura/cabeceras.test.ts        E1
frontend/index.html                                  E2 (sin Google)
frontend/public/fuentes/*.woff2                      E2 (si P1 = self-host)
frontend/src/estilos/fuentes.css                     E2 (si P1 = self-host)
frontend/src/test/index_html.test.ts                 E2
frontend/src/api/supabase.ts / supabase.test.ts      E3
frontend/e2e/seguridad.spec.ts                       E1, E3
supabase/migrations/0007_fijar_idioma.sql            E4 (tras la aprobación)
backend/app/api/usuarios.py                          E4
backend/tests/integration/test_api_usuarios.py       E4
backend/tests/integration/test_usuarios_repo.py      E4 (suma)
backend/app/api/limites.py                           límites por tenant
backend/tests/integration/test_pii_en_logs.py        PII
docs/seguridad/revision-002-008.md                   revisión + E5
```

## Preguntas abiertas

Sin decidir. La columna "Propuesta" es **propuesta pendiente de Daniel**: no se aplica hasta que la apruebe.

| Id | Pregunta | Propuesta (pendiente de Daniel) |
|----|----------|---------------------------------|
| P1 | Fuentes (E2): ¿self-host de DM Sans y Poppins o permitir `fonts.googleapis.com` y `fonts.gstatic.com` en la CSP? | Servir las fuentes desde el propio sitio, sin Google. |
| P2 | Sesión (E3): ¿`sessionStorage` (cerrar la pestaña cierra la sesión, no se comparte entre pestañas) o seguir con `localStorage`? | Sí, la sesión va a `sessionStorage`. |
| P3 | Login (E5): ¿el rate limit de Supabase Auth alcanza y el riesgo sigue aceptado? ¿Hace falta el check manual por Management API? | Sigue aceptado; Daniel copia los límites del panel a `docs/seguridad/revision-002-008.md`, sin check por Management API. |
| P4 | Número de migración (E4): ¿quién numera primero, la 012 o la 006? | 0007 queda reservada para `fijar_idioma`; la 006 toma la siguiente libre (0008) y renumera si choca. |
| P5 | Proxy same-origin: sin cookie de refresh, ¿vale la pena? | Fuera del [MIN]. Si se hace, rewrite de `vercel.json` `/api/(.*)` → api en Railway, no Caddy. |
| P6 | Spec: ¿se enmienda `spec.md` para Supabase Auth y Vercel, o alcanza con la tabla "Qué cambió desde la spec"? | Sí, enmendar la spec marcando lo reemplazado, sin borrarlo. |
| P7 | Orden de corte: la spec corta cumplimiento → E2E de sesión → `SESSION_SECRET_ANTERIOR` → límites de intake/importar; los dos del medio ya no existen. | Cumplimiento → límites por tenant → proxy (P5). |

## Complexity Tracking

Sin violaciones de la constitución. `fijar_idioma` es una segunda función `SECURITY DEFINER`; la justifica que `app_rt` no tiene `UPDATE` sobre `usuarios` (0006) y no debe tenerlo.
