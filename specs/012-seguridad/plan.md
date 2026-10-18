# Implementation Plan: 012 — Seguridad: cabeceras, CSP, sesión del front, idioma del usuario y límites

**Branch**: `feature/012-seguridad` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

> La spec es anterior a la decisión de Supabase Auth (005 plan:335, constitución 2.0.0). Este plan no la reescribe: marca qué partes quedan superadas ("Qué cambió desde la spec") y planifica lo que sigue valiendo, más cinco entradas nuevas que pidió el dueño (E1–E5). Lo que la spec no decide va a **Preguntas abiertas**, con un default propuesto que no se aplica hasta que lo apruebe el dueño.
>
> Artefactos: como en la 002, la 005 y la 011, este slice entrega solo `plan.md` y `tasks.md`.

## Summary

La 012 entrega:
- **E1.** CSP y cabeceras de seguridad en `frontend/Caddyfile`, con `check_cabeceras.sh` y su test de que el check puede fallar;
- **E2.** las fuentes de Google fuera de `index.html` (o permitidas en la CSP, P1), con un test que lo fija;
- **E3.** la sesión de supabase-js fuera de `localStorage` (o la decisión escrita de dejarla, P2);
- **E4.** `PATCH /usuarios/me` con la función `fijar_idioma` (`SECURITY DEFINER`), DDL **pendiente de aprobación de Daniel**;
- **E5.** el rate limit del login: sigue como riesgo aceptado (005 plan:357); la 012 solo deja escrito y verificable qué límite pone Supabase Auth;
- lo de la spec que sigue vigente: revisión `security` de 002–008, PII transversal en logs (middleware de errores y 422 sin `input`), límites por tenant en las rutas que gastan créditos y la pantalla de cumplimiento.

## Technical Context

- **Back:** Python 3.12, FastAPI, SQLAlchemy Core, Postgres con RLS; rol de runtime `app_rt` sin `BYPASSRLS`. Migraciones con Supabase CLI en `supabase/migrations/`.
- **Auth:** Supabase Auth. El front loguea con supabase-js; la api verifica el JWT por JWKS (ES256/RS256, `aud=authenticated`, `iss=AUTH_ISSUER`) y saca el tenant de `tenant_de_usuario(sub)`, nunca del token.
- **Front:** React, Vite, Vitest, Playwright. Servido por Caddy (`frontend/Caddyfile`, `admin off`, `:{$PORT:8080}`).
- **Tests:** `scripts/test-backend.sh [ruta]`, `scripts/test-frontend.sh`. Scripts de CI con su `test_*.sh` en `.github/scripts/`, como `check_imagen.sh`.

## Constitution Check

- **Principio V (seguridad por PR):** CodeQL (default setup), `required-checks.txt`, gitleaks y `revision-seguridad` ya están en `main` (PR #23, 31b9ce2). La 012 no los rehace; los cita (D2).
- **Principio VI (PII nunca en logs):** el test transversal de la spec sigue vigente (Fase 4).
- **Principio VII (tenant por RLS):** `fijar_idioma` filtra por `tenant_id = current_setting('app.tenant_id')` además de `auth_user_id`; lo prueba `test_fijar_idioma_no_cruza_tenants` con mutación (E4).
- **Migraciones:** el DDL va en este plan marcado **PENDIENTE DE APROBACIÓN DE DANIEL**. No se crea ningún archivo en `supabase/migrations/` hasta esa aprobación (T001, T020).

## Dependencias externas

| Id | Qué | ¿En `main`? | Para qué |
|----|-----|-------------|----------|
| D1 | 005 back: `usuarios`, `tenant_de_usuario`, `ALTER DEFAULT PRIVILEGES … REVOKE EXECUTE` (migración 0006), verificador JWKS | **Sí** (5edee68) | E4 copia el patrón de `tenant_de_usuario`; los tests usan sus fixtures (`test_usuarios_repo.py`). |
| D2 | 012 config del repo: CodeQL default setup, `required-checks.txt`, gitleaks, `revision_seguridad.sh`, `veredicto_security.sh`, `verificar_proteccion.sh`, `test_required_checks.py` | **Sí** (PR #23, 31b9ce2) | Paso 2 de la spec: hecho. Queda solo el pendiente humano de `ANTHROPIC_API_KEY`. |
| D3 | 005 back: `GET /usuarios/me` (idiomas del usuario y del tenant) | **No** (`rg "usuarios/me" backend` vacío; los routers de `main` son `auth`, `busquedas`, `tablero`, `actividades`) | `test_fijar_idioma_persiste` lee con el GET. Sin D3, E4 trae su propio GET mínimo o espera (T001). |
| D4 | 005 front: `SelectorIdioma.tsx` manda `PATCH /usuarios/me {idioma}`, `sesion.ts`, `supabase.ts` | **Sí** (el front ya llama una ruta que no existe y traga el error con `.catch`) | E3 y E4. |
| D5 | 006 enriquecedor: su plan y su migración | **No** (sin plan ni migración en `main`) | Número de migración de E4: la 006 puede tomar 0007 primero (T001). |
| D6 | 007 (`RUTAS_PUBLICAS`, `/baja/{token}`), 008 (`/calificaciones/importar`), 009 (`/webhooks/whatsapp`) | **No** (`rg` sin rutas en `backend/app`) | Límites por tenant y casos de PII de esas rutas: entran solo las que estén en `main` al arrancar la fase. |
| D7 | 001: `check_imagen.sh` y su test, `frontend/Dockerfile` | **Sí** | Patrón de `check_cabeceras.sh`. |

## Qué cambió desde la spec (Supabase Auth)

La spec diseña una sesión propia. Con Supabase Auth esas partes no se construyen; se listan para que no se pierdan en silencio:

| Parte de la spec | Estado | Por qué |
|------------------|--------|---------|
| Qué hace §1: refresh opaco en cookie `HttpOnly`, rotación de un solo uso, tope de 8 h, `SESSION_SECRET` rotable | **Superado** | El refresh lo emite y rota Supabase Auth. La api no firma tokens. |
| `test_refresco.py` entero y los tests de sesión de `test_auth.py` (cookie, `/auth/refrescar`, `/auth/salir`, `Origin`, `sesiones_refresco`, `SESSION_SECRET_ANTERIOR`) | **Superado** | No hay `/auth/sesion` propio: lo fija `test_sin_login_propio.py` (005). |
| Rate limit de `/auth/sesion`, semáforo de scrypt, 429 igual exista o no el email | **Superado → E5** | No hay scrypt ni login en la api. Riesgo aceptado (005 plan:357). |
| `cliente.test.ts`: access en memoria, single-flight del refresh, 409 en curso, restaurar al cargar | **Superado → E3** | El refresh lo hace supabase-js. Lo que queda es dónde guarda la sesión. |
| Proxy same-origin (`/api/*` por la red privada de Railway) | **Sigue, sin urgencia** | Se justificaba por la cookie `SameSite=Strict`. Sin cookie, el proxy solo achica la CSP (`connect-src 'self'` para la api). Fuera del [MIN]: P5. |
| `test_dockerfile_web_no_recibe_args` | **Choca** | `frontend/Dockerfile` necesita `VITE_SUPABASE_URL` y `VITE_SUPABASE_PUBLISHABLE_KEY` (públicas por diseño, 005 plan:359). El test pasa a "solo estos tres ARG" o "solo los dos de Supabase" si entra el proxy. |
| CSP de la spec con `connect-src 'self'` | **Cambia (E1)** | Bloquearía las llamadas de supabase-js a `VITE_SUPABASE_URL`. Suma ese origen, y el de la api mientras no haya proxy. |
| Revisión `security` 002–008, PII transversal, límites por tenant, pantalla de cumplimiento, `check_cabeceras.sh` | **Sigue** | No dependen de cómo se loguea. |

Si el dueño quiere la spec enmendada, va en un PR aparte (P6).

## Diseño por entrada

### E1 — CSP y cabeceras en `frontend/Caddyfile`

Hoy el Caddyfile no pone ninguna cabecera. Se suma, dentro del bloque del sitio:

```
header {
	Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' {$SUPABASE_ORIGEN} {$API_ORIGEN}; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
	Strict-Transport-Security "max-age=31536000; includeSubDomains"
	X-Content-Type-Options "nosniff"
	Referrer-Policy "no-referrer"
	Permissions-Policy "camera=(), microphone=(), geolocation=()"
	Cross-Origin-Opener-Policy "same-origin"
	-Server
}
request_body {
	max_size 1MB
}
```

- `SUPABASE_ORIGEN` y `API_ORIGEN` son variables de entorno de `web` en tiempo de arranque (Caddy las lee con `{$VAR}`), no del bundle. Son orígenes, sin path.
- `style-src` y `font-src` quedan en `'self'` solo si E2 se resuelve con self-host (P1).
- `/health` también lleva las cabeceras: el bloque `header` va fuera de los `handle`.

**Test propuesto** (`.github/scripts/check_cabeceras.sh` + `.github/scripts/test_check_cabeceras.sh`, patrón de `check_imagen.sh`):
- el script levanta la imagen `web` con `SUPABASE_ORIGEN=https://proyecto.supabase.co` y `API_ORIGEN=https://api.ejemplo.invalid`, y en `/` y en `/ruta-spa` verifica la CSP **exacta**, HSTS, `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, COOP y que **no** venga `Server`;
- un POST de 2 MB da 413;
- `test_check_cabeceras.sh` corre el script contra un Caddyfile sin la línea de CSP y espera salida ≠ 0, y contra uno con `connect-src 'self'` sin el origen de Supabase y espera ≠ 0. Un check que no puede fallar no prueba nada.
- **Rojo:** hoy el script falla en el primer assert (no hay CSP).
- **E2E** (`frontend/e2e/seguridad.spec.ts::navegar_no_viola_la_csp`): login → tablero → Nueva búsqueda con 0 eventos `securitypolicyviolation`. Corre contra el deploy en `e2e.yml`, apenas la CSP está arriba.

### E2 — Google Fonts sin CSP en `index.html`

`frontend/index.html` hace `preconnect` a `fonts.googleapis.com` y `fonts.gstatic.com` y carga el CSS de DM Sans y Poppins desde Google. Con la CSP de E1, `style-src 'self'` y `font-src 'self'` lo bloquean: la página carga con la fuente del sistema y el E2E de CSP da rojo.

Dos caminos (fork real, P1):
- **Self-host (default propuesto):** los `.woff2` en `frontend/public/fuentes/` con su `@font-face` en el CSS del proyecto. La CSP no cambia, no hay request a Google (sin IP del usuario a un tercero) y no hay dependencia de red externa en la demo. Costo: bajar los archivos una vez y revisar la licencia (OFL, permite redistribuir).
- **Permitir Google:** `style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com`. Cero archivos nuevos, pero la CSP se abre a un tercero y cada visita le avisa a Google.

**Test propuesto:**
- `frontend/src/test/index_html.test.ts::no_carga_recursos_de_terceros`: lee `index.html` y falla si aparece cualquier `href` o `src` con `https://` (con self-host), o si aparece un origen que no está en la CSP del Caddyfile (si se permite Google). **Rojo:** hoy encuentra `fonts.googleapis.com`.
- El E2E `navegar_no_viola_la_csp` de E1 lo cubre en el navegador real.
- **Mutación:** volver a pegar el `<link>` de Google → rojo.

### E3 — Sesión de supabase-js en `localStorage`

`frontend/src/api/supabase.ts` llama `createClient(url, key)` sin `auth.storage`: supabase-js guarda access y refresh en `localStorage` (`sb-<ref>-auth-token`). Persiste al cerrar el navegador y lo comparten todas las pestañas.

- **`sessionStorage` (default propuesto):** `createClient(url, key, { auth: { storage: sessionStorage } })`. La sesión muere al cerrar la pestaña y no se comparte entre pestañas.
- **Lo que no cambia:** ante un XSS, `sessionStorage` está tan expuesto como `localStorage`. La mitigación real del robo de token es la CSP de E1; E3 achica la ventana (sesiones olvidadas en una máquina compartida), no el vector.
- **Costo de UX (P2):** abrir un link en otra pestaña pide login de nuevo. Para la demo, una sola pestaña.

**Test propuesto:**
- `frontend/src/api/supabase.test.ts::la_sesion_va_a_sessionStorage`: con `vi.mock("@supabase/supabase-js")` espía (`supabaseFalso.ts` ya exporta `moduloFalso`), importar `supabase.ts` y asertar que el tercer argumento de `createClient` trae `auth.storage === window.sessionStorage`. **Rojo:** hoy el argumento es `undefined`.
- **Mutación:** sacar `storage` → rojo.
- E2E `seguridad.spec.ts::el_token_no_queda_en_localStorage`: después del login, ninguna clave de `localStorage` empieza con `sb-` y termina en `-auth-token`.
- `frontend/src/test/setup.ts:23` ya limpia `sessionStorage` entre tests; no hace falta tocarlo.

### E4 — `PATCH /usuarios/me` con `fijar_idioma` (SECURITY DEFINER)

El front ya manda `PATCH /usuarios/me {idioma}` (`SelectorIdioma.tsx:16`) y la api no tiene la ruta: hoy da 404 y el `.catch` lo traga. `app_rt` no tiene privilegios sobre `usuarios` (0006), así que el UPDATE va por función `SECURITY DEFINER`, con el mismo patrón que `tenant_de_usuario`.

**Ruta:** `PATCH /usuarios/me`, autenticada. Body `IdiomaUsuario(BaseModel, extra="forbid")` con `idioma: Literal["es", "en"]`. El `auth_user_id` sale del `sub` verificado, nunca del body. Llama `fijar_idioma(sub, idioma)` dentro de la transacción con `app.tenant_id` ya seteado. Responde **204**. Si la función cambió 0 filas, 404 (el usuario no es de este tenant).

**DDL — PENDIENTE DE APROBACIÓN DE DANIEL**

Archivo propuesto: `supabase/migrations/0007_fijar_idioma.sql`. El número se confirma en T001 contra la 006 (D5). **No se crea el archivo hasta la aprobación.**

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
- `backend/tests/integration/test_api_usuarios.py::test_fijar_idioma_persiste`: usuario de tenant A con `idioma='es'`; `PATCH /usuarios/me {idioma:'en'}` da 204, y el `GET /usuarios/me` siguiente (o un SELECT como `postgres` si D3 no está) trae `'en'`. **Rojo:** hoy la ruta da 404.
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
2. `.github/scripts/test_check_cabeceras.sh` y `.github/scripts/check_cabeceras.sh`.
3. `scripts/test-frontend.sh` (incluye `supabase.test.ts` e `index_html.test.ts`).
4. `e2e.yml` contra el deploy: `seguridad.spec.ts`.

## Project Structure

```
frontend/Caddyfile                                   E1 (header, request_body)
frontend/index.html                                  E2 (sin Google)
frontend/public/fuentes/*.woff2                      E2 (si P1 = self-host)
frontend/src/estilos/fuentes.css                     E2 (si P1 = self-host)
frontend/src/test/index_html.test.ts                 E2
frontend/src/api/supabase.ts / supabase.test.ts      E3
frontend/e2e/seguridad.spec.ts                       E1, E3
.github/scripts/check_cabeceras.sh / test_…sh        E1
supabase/migrations/0007_fijar_idioma.sql            E4 (tras la aprobación)
backend/app/api/usuarios.py                          E4
backend/tests/integration/test_api_usuarios.py       E4
backend/tests/integration/test_usuarios_repo.py      E4 (suma)
backend/app/api/limites.py                           límites por tenant
backend/tests/integration/test_pii_en_logs.py        PII
docs/seguridad/revision-002-008.md                   revisión + E5
```

## Preguntas abiertas

Sin decidir. El default propuesto no se aplica hasta que lo apruebe el dueño.

- **P1 — Fuentes (E2):** ¿self-host de DM Sans y Poppins o permitir `fonts.googleapis.com` y `fonts.gstatic.com` en la CSP? Default propuesto: self-host.
- **P2 — Sesión (E3):** ¿`sessionStorage` (cerrar la pestaña cierra la sesión, no se comparte entre pestañas) o seguir con `localStorage`? Default propuesto: `sessionStorage`.
- **P3 — Login (E5):** ¿el rate limit de Supabase Auth alcanza y el riesgo sigue aceptado? ¿Hace falta el check manual por Management API? Default propuesto: sigue aceptado, sin check.
- **P4 — Número de migración (E4):** 0007 si la 006 no lo toma antes. ¿Quién numera primero? Default propuesto: el primero que mergea a `main`; el otro renumera.
- **P5 — Proxy same-origin:** sin cookie de refresh, ¿sigue valiendo el trabajo de Railway (red privada, sacar el dominio público de la api)? Default propuesto: fuera del [MIN], `API_ORIGEN` en la CSP mientras tanto.
- **P6 — Spec:** ¿se enmienda `spec.md` para Supabase Auth en un PR aparte, o alcanza con la tabla "Qué cambió desde la spec"? Default propuesto: la tabla.
- **P7 — Orden de corte:** la spec corta cumplimiento → E2E de sesión → `SESSION_SECRET_ANTERIOR` → límites de intake/importar. Los dos del medio ya no existen. ¿Nuevo orden: cumplimiento → límites por tenant → proxy (P5)? Default propuesto: ese.

## Complexity Tracking

Sin violaciones de la constitución. `fijar_idioma` es una segunda función `SECURITY DEFINER`; la justifica que `app_rt` no tiene `UPDATE` sobre `usuarios` (0006) y no debe tenerlo.
