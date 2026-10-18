# Tasks: 012 — Seguridad: cabeceras, CSP, sesión del front, idioma del usuario y límites

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [checklists/requirements.md](./checklists/requirements.md)

**Formato**: `- [ ] TNNN [P?] [Paso n] descripción con ruta`

- **Rojo:** un test que falla en un `assert` sobre el resultado. Nunca `xfail`, `ImportError` ni `AttributeError`. Si el símbolo no existe, primero el esqueleto que devuelve algo incorrecto.
- **Mutación:** un cambio de una línea en el código de producción que tiene que poner el test en rojo. Si no lo pone, el test no prueba nada y se reescribe.
- **(advisor)** y **(security)** son paradas: no se sigue hasta que el revisor aprueba.
- **Dueños:** `swarm` (inventario), `lead` (rojo y verde), `advisor` (revisa tests y diseño), `security` (revisa CSP, sesión, `fijar_idioma` y la revisión 002–008), **Daniel** (DDL, deploy, paneles de Vercel, Railway y Supabase, decisiones de producto).
- **[MIN]** entra al mínimo funcional; **[Pulido]** después.
- E1–E5 y D1–D7 son los de [plan.md](./plan.md).

## Fase 1: Puerta y setup

- [ ] T001 [Paso 0] [MIN] `swarm`: `git fetch origin`; confirmar en `origin/main` el estado de D1–D7 (tabla del plan, verificada en 550928d) y escribir el resultado en el PR. Confirmar que `supabase/migrations/` sigue sin una 0007: la migración de E4 está **fijada en 0007** (P4); si otra rama la tomó, avisar a Daniel antes de seguir.
- [ ] T002 [Paso 0] [MIN] **Daniel**: responder P1 (fuentes) y P2 (sesión). Las propuestas del plan (self-host, `sessionStorage`) no se aplican sin su respuesta.

## Fase 2: E1 — CSP y cabeceras en `frontend/vercel.json`

- [ ] T010 [P] [Paso 1] [MIN] `lead` **Rojo**: `frontend/tests/arquitectura/cabeceras.test.ts`: parsea `frontend/vercel.json` y para `source: "/(.*)"` exige la CSP **exacta** (directiva por directiva), HSTS, `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` y COOP; `connect-src` con `'self'`, un origen `https://<ref>.supabase.co` y el origen de la api (más los de `VITE_SUPABASE_URL` / `VITE_API_URL` si están seteadas); y que el rewrite a `/index.html` siga. Hoy falla en el assert porque `vercel.json` no tiene `headers`. Pegar el output.
- [ ] T011 (advisor) Revisa T010: que la CSP se compare exacta (no `contains`), que el test lea el `vercel.json` real y no una copia, y que falle por el motivo correcto.
- [ ] T012 [Paso 1] [MIN] **Daniel**: dictar los dos orígenes públicos de `connect-src` (el de `VITE_SUPABASE_URL` y el de `VITE_API_URL` cargadas en Vercel). Son públicos; ningún secreto va a `vercel.json`.
- [ ] T013 [Paso 1] [MIN] `lead` **Verde**: bloque `headers` en `frontend/vercel.json` (plan §E1), con los dos orígenes literales de T012 y sin tocar el rewrite. T010 en verde.
- [ ] T014 [Paso 1] [MIN] **Mutación** `lead`: sacar `frame-ancestors 'none'` → T010 rojo. Sacar el origen de Supabase de `connect-src` → rojo. Restaurar.
- [ ] T016 [Paso 1] [MIN] **Daniel**: deploy en Vercel y `curl -sI https://www.profitdata.tech/` con la CSP en la respuesta. Frontera humana.
- [ ] T017 [Paso 1] (security) Revisa la CSP final: sin `'unsafe-inline'`, sin `'unsafe-eval'`, sin comodines, `connect-src` solo con `'self'` y los dos orígenes.

## Fase 3: E2 — Google Fonts fuera de `index.html`

- [ ] T020 [P] [Paso 2] [MIN] `lead` **Rojo**: `frontend/src/test/index_html.test.ts::no_carga_recursos_de_terceros`: lee `frontend/index.html` y falla si hay un `href` o `src` con `https://` (P1 = self-host) o con un origen que no está en la CSP de `vercel.json` (P1 = permitir Google). Hoy falla en el assert por `fonts.googleapis.com`.
- [ ] T021 [Paso 2] [MIN] `lead` **Verde** (P1 = self-host): DM Sans 400/500/700 y Poppins 500/600/700 en `frontend/public/fuentes/*.woff2`, `@font-face` en `frontend/src/estilos/fuentes.css`, y fuera los tres `<link>` de Google de `index.html`. Con P1 = permitir Google: sumar `https://fonts.googleapis.com` a `style-src` y `https://fonts.gstatic.com` a `font-src` en `vercel.json` y en `cabeceras.test.ts`. T020 en verde.
- [ ] T022 [Paso 2] [MIN] **Mutación** `lead`: volver a pegar el `<link>` de Google en `index.html` → T020 rojo. Restaurar.
- [ ] T023 [Paso 2] `swarm`: confirmar la licencia OFL de las dos familias y anotarla en el PR (solo si P1 = self-host).

## Fase 4: E3 — Sesión de supabase-js

- [ ] T030 [P] [Paso 3] [MIN] `lead` **Rojo**: `frontend/src/api/supabase.test.ts::la_sesion_va_a_sessionStorage`: `vi.mock("@supabase/supabase-js")` con un `createClient` espía (sobre `moduloFalso` de `frontend/src/test/supabaseFalso.ts`), importar `supabase.ts` y asertar que el tercer argumento trae `auth.storage === window.sessionStorage`. Hoy falla porque el argumento es `undefined`.
- [ ] T031 (advisor) Revisa T030: que el assert sea sobre el argumento que recibe `createClient`, no sobre un mock que se devuelve a sí mismo.
- [ ] T032 [Paso 3] [MIN] `lead` **Verde**: `createClient(url, key, { auth: { storage: window.sessionStorage } })` en `frontend/src/api/supabase.ts`. T030 en verde.
- [ ] T033 [Paso 3] [MIN] **Mutación** `lead`: sacar `storage` → T030 rojo. Restaurar.
- [ ] T034 [Paso 3] (security) Revisa E3 junto con la CSP: deja escrito en el PR que `sessionStorage` achica la ventana, no el vector XSS, y que la mitigación es T013.

## Fase 5: E4 — `PATCH /usuarios/me` con `fijar_idioma`

- [ ] T040 [Paso 4] [MIN] **Daniel**: aprobar el DDL de `fijar_idioma` (plan §E4, **PENDIENTE DE APROBACIÓN DE DANIEL**) como `0007_fijar_idioma.sql`. Sin aprobación no se crea el archivo en `supabase/migrations/` y la fase espera.
- [ ] T041 [Paso 4] [MIN] `lead`: esqueleto sin DDL de producción: en el router que ya existe (`backend/app/api/usuarios.py`, #40) sumar `PATCH /usuarios/me` con `Depends(sesion_actual)`, que devuelve 204 sin escribir nada, y `IdiomaUsuario(BaseModel)` **sin** `extra="forbid"` y con `idioma: str`. El esqueleto existe para que los rojos fallen en un `assert`, no en un 404 ni en un import.
- [ ] T042 [P] [Paso 4] [MIN] `lead` **Rojo**: `backend/tests/integration/test_api_usuarios.py::test_fijar_idioma_persiste`: usuario de tenant A con `idioma='es'`; `PATCH {idioma:'en'}` da 204 y el `GET /usuarios/me` siguiente (D3) trae `idioma_usuario: 'en'`. Falla en el assert del idioma.
- [ ] T043 [P] [Paso 4] [MIN] `lead` **Rojo**: `::test_fijar_idioma_invalido_da_422[caso]` con `pt`, `''`, `EN` y los tres de mass assignment (`{idioma:'en', usuario_id:…}`, `{…, tenant_id:<B>}`, `{…, auth_user_id:<otro>}`): cada uno da 422, el cuerpo no trae `input`, y la fila sigue igual. Falla porque el esqueleto da 204.
- [ ] T044 [P] [Paso 4] [MIN] `lead` **Rojo**: `backend/tests/integration/test_usuarios_repo.py::test_fijar_idioma_no_cruza_tenants`: como `app_rt`, con `app.tenant_id = A`, `fijar_idioma(usuario_de_A, 'en')` devuelve 1; con `app.tenant_id = B`, `fijar_idioma(usuario_de_A, 'es')` devuelve 0 y la fila sigue en `'en'`. Corre contra la función creada en la base de test por la fixture con el DDL aprobado; antes de T040 se queda en la rama sin mergear.
- [ ] T045 [P] [Paso 4] [MIN] `lead` **Rojo**: parametrizar `test_tenant_de_usuario_es_security_definer_con_search_path` (`test_usuarios_repo.py:51`) a `[tenant_de_usuario|fijar_idioma]`: `prosecdef`, `proconfig` con `search_path=public, pg_temp`, sin `EXECUTE` para `PUBLIC`, `anon` ni `authenticated`. Sumar `::test_fijar_idioma_sin_tenant_seteado_falla`: sin `SET app.tenant_id` la llamada levanta error y no cambia filas. Fallan porque la función no existe todavía en la base: el assert es sobre `pg_proc`, no un error de import.
- [ ] T046 (security) Revisa T042–T045 **antes** de aceptarlos: los tres que pidió (`persiste`, `invalido_da_422` con mass assignment, `no_cruza_tenants`), que cada uno asierte sobre la fila y no solo el status, y que el `sub` salga del token verificado y nunca del body.
- [ ] T047 (advisor) Revisa el diseño de la ruta y el puerto: 204 con 1 fila, 404 con 0, la transacción con `app.tenant_id` ya seteado.
- [ ] T048 [Paso 4] [MIN] `lead` **Verde**: crear `supabase/migrations/0007_fijar_idioma.sql` con el DDL **aprobado en T040, sin cambios**. `IdiomaUsuario` con `extra="forbid"` e `idioma: Literal["es","en"]`; la ruta llama `fijar_idioma(sub, idioma)` y devuelve 204 o 404. T042–T045 en verde.
- [ ] T049 [Paso 4] [MIN] **Mutaciones** `lead`, una por vez, cada una pone en rojo su test:
  - sacar `AND tenant_id = current_setting(...)` → `test_fijar_idioma_no_cruza_tenants` rojo;
  - sacar `extra="forbid"` → los casos de mass assignment de T043 rojos;
  - cambiar `Literal` por `str` → `pt` y `EN` rojos;
  - sacar `SET search_path` → T045 rojo.
  Restaurar.
- [ ] T050 [Paso 4] `lead`: actualizar `test_migraciones.py` / `test_migracion_0006.py` si enumeran las migraciones esperadas, y el caso de `PATCH /usuarios/me` en `CASOS_PII` (Fase 6).
- [ ] T051 [Paso 4] **Daniel**: aplicar la migración en el proyecto de Supabase. Frontera humana.

## Fase 6: Lo que sigue de la spec

- [ ] T060 [Paso 5] [MIN] `security`: revisión de 002–008 contra lo que está en `main` al arrancar (D6), reporte en `docs/seguridad/revision-002-008.md`. Va **primero** entre las tareas de la spec.
- [ ] T061 [Paso 5] [MIN] `lead` **Rojo**: `backend/tests/integration/test_pii_en_logs.py` con `CASOS_PII` (incluye `PATCH /usuarios/me` con un idioma inválido): ni el email, ni el body, ni el `input` del 422 aparecen en los logs capturados. Falla hoy porque el 422 de FastAPI trae `input`.
- [ ] T062 [Paso 5] [MIN] `lead` **Verde**: `exception_handler` de `RequestValidationError` que saca `input` y `ctx`; `--no-access-log` en el arranque de la api. **Mutación:** devolver `exc.errors()` crudo → T061 rojo.
- [ ] T063 [Paso 6] `lead` **Rojo**: `backend/tests/integration/test_limites.py` para `vista-previa` (30/h) y `ejecutar` (10/h) por tenant, con `test_429_no_toca_adaptadores_ni_costos` y `test_limites_no_usan_la_ip`. Sin los casos de login ni scrypt (superados, plan "Qué cambió"). Las rutas de D6 entran solo si están en `main`.
- [ ] T064 [Paso 6] `lead` **Verde**: `backend/app/api/limites.py` en memoria con `ponytail:` sobre el proceso único. **Mutación:** usar la IP como clave → `test_limites_no_usan_la_ip` rojo.
- [ ] T065 (advisor) Revisa T063–T064.
- [ ] T066 [Paso 7] [Pulido] `lead`: pantalla de cumplimiento, tal como la spec. Primera en el orden de corte.

## Fase 7: E5 — Rate limit del login

- [ ] T070 [Paso 8] **Daniel**: copiar de Supabase (Authentication → Rate Limits) los valores vigentes a `docs/seguridad/revision-002-008.md`, sección "Login". Frontera humana: el panel es de Daniel.
- [ ] T071 [Paso 8] `security`: con esos valores, recomendar en el mismo documento si el riesgo sigue aceptado (P3). No construye limitador: `test_sin_login_propio.py` ya fija que la api no tiene login.

## Fase 8: E2E de seguridad

- [ ] T080 [Paso 9] [MIN] `lead` **Rojo**: `frontend/e2e/seguridad.spec.ts`:
  - `navegar_no_viola_la_csp`: login → tablero → Nueva búsqueda con 0 eventos `securitypolicyviolation`;
  - `el_token_no_queda_en_localStorage`: después del login, ninguna clave de `localStorage` con forma `sb-*-auth-token`.
  Contra el deploy previo a T013 y T032, los dos fallan en el assert.
- [ ] T081 [Paso 9] [MIN] `lead` **Verde**: con T013, T021, T032 deployados en Vercel (T016), los dos en verde en `e2e.yml`.

## Dependencias y paralelismo

- T001 y T002 bloquean todo.
- Las fases 2, 3, 4 y 6 son independientes entre sí: un `lead` por fase.
- La Fase 3 depende de la 2 solo si P1 = permitir Google (cambia la CSP).
- La Fase 5 espera la aprobación de T040 para T048; T041–T047 pueden avanzar antes, sin mergear.
- La Fase 8 va al final: necesita deploy de E1, E2 y E3.
- Los [P] dentro de una fase se escriben en paralelo.

## Orden de corte

Si falta tiempo, se corta en este orden (P7, propuesta pendiente de Daniel):
1. pantalla de cumplimiento (T066);
2. límites por tenant (T063–T065);
3. proxy same-origin (P5, no está en estas tareas).

Nunca se cortan: CSP y cabeceras (Fase 2), los tests de `fijar_idioma` que pidió `security` (T042–T046), PII en logs (T061–T062) y la revisión 002–008 (T060).

## Estrategia: primero que funcione

1. Fase 2 (CSP en `vercel.json`) y Fase 4 (sesión): dos archivos, sin base, cierran la superficie XSS.
2. Fase 3 (fuentes): la CSP no rompe la tipografía.
3. Fase 5 (idioma): el `PATCH` del `SelectorIdioma` deja de dar 405.
4. Fase 6 y 7: revisión, PII y límites.
5. Fase 8: E2E contra el deploy.
