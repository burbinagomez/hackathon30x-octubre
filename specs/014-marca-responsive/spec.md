# Spec 014 — Marca Dapta y responsive

**Slice:** 014 · **Rama:** `feature/014-marca-responsive` · **Tiempo:** ≤ 1,5 h
**Depende de:** 001 (front con la página de health). **Desbloquea:** todo slice con UI (005, 007, 008, 010…), que hereda los tokens y la regla responsive.

## Para quién
- **El jurado y la audiencia de Dapta:** el demo se ve como un producto de Dapta, también en el celular de quien lo mira.
- **El equipo:** los slices con UI arrancan con tokens, tipografía y una regla responsive ya escrita y con su test, en vez de decidir colores y breakpoints cada uno.

## Qué hace
- **Tokens** de Dapta como variables CSS en `:root`, en `frontend/src/tokens.css`: `--color-acento: #CBE850`, `--color-oscuro: #1A1A1C`, `--color-fondo: #FFFFFF`, `--color-gris: #9B9999`, `--fuente-titulos` (Poppins) y `--fuente-texto` (DM Sans). Ningún archivo de `src/` fuera de `tokens.css` escribe estos hex: usa la variable. `tokens.css` también lleva las reglas de `body` y `h1`–`h6`, así lo que lee Vitest es lo mismo que carga la app. Se importa en `main.tsx`, no en `App.tsx`.
- **Tipografía:** DM Sans para texto (en `body`) y Poppins para títulos, con la regla `h1, h2, h3, h4, h5, h6 { font-family: var(--fuente-titulos) }` en `tokens.css`. La página de health no suma título visible: la regla queda lista para los slices siguientes. Las fuentes se cargan desde Google Fonts en `frontend/index.html`, con `<link rel="preconnect">` a `fonts.googleapis.com` y a `fonts.gstatic.com`, y `display=swap`.
- **Viewport:** `index.html` suma `<meta name="viewport" content="width=device-width, initial-scale=1">`. Sin esa línea, un navegador móvil dibuja la página en un layout de ~980 px y el test de móvil no mide lo que debe.
- **Contraste:** el lima nunca va como color de texto sobre blanco (no llega a contraste legible). Va de fondo con texto `#1A1A1C` encima, o como texto/acento sobre el oscuro.
- **`body`** usa los tokens, con la regla en `tokens.css`: `background: var(--color-fondo)`, `color: var(--color-oscuro)`, `font-family: var(--fuente-texto)`. El texto visible no cambia ("API: ok · DB: ok"): `App.test.tsx` y `e2e/health.spec.ts` siguen pasando sin tocarlos.
- **`vite.config.ts`** suma `test.css: { include: [/\?raw/] }`. Con la config actual, el plugin `vitest:css-disable` vacía todo CSS, así que `import t from "./tokens.css?raw"` da vacío y cualquier aserción negativa nacería verde. Sin dependencias nuevas.

## Regla transversal: responsive en todo slice con UI
Vale para este slice y para todos los siguientes que toquen UI. Cada uno la cumple en su propio PR:
1. **Mobile-first:** estilos base para móvil; `min-width` en media queries para crecer.
2. **Mínimo 360 px** de ancho sin romper el layout.
3. **Sin scroll horizontal** de la página: `document.documentElement.scrollWidth <= clientWidth`.
4. **Objetivos táctiles de al menos 44 × 44 px** (botones, links, controles).
5. **Tablas en móvil:** pasan a tarjetas, o hacen scroll horizontal dentro de su propio contenedor (`overflow-x: auto`), nunca de la página.

**Chequeo:** `frontend/e2e/marca-responsive.spec.ts` recorre una lista `RUTAS` (hoy solo `/`) en los tres viewports de abajo. Cada slice con UI agrega sus rutas a `RUTAS`.
**Dónde queda escrita:** una fila nueva en `docs/decisiones.md` (Fecha `2026-10-17` | Decisión | Razón | Fuente). Sube a la constitución cuando haya router y `RUTAS` cubra las pantallas reales.

## Restricciones
- **Sin Tailwind ni dependencias nuevas.** CSS plano; `package.json` no cambia.
- **Sin `node:fs` en los tests:** no hay `@types/node` y `tsc` compila los tests. Los archivos se leen con `?raw` y `import.meta.glob`.
- **Idiomas es/en:** la UI sigue existiendo en los dos idiomas. Este slice no agrega texto visible nuevo.
- **No se modifican** `frontend/playwright.config.ts` ni `frontend/e2e/health.spec.ts`: los usa `e2e.yml` para T032.
- **Google Fonts:** aceptable para el demo (le pasa a Google la IP del visitante). Lo revisa `security` en el PR.

## Terminado cuando (tests que hoy fallan)
- `frontend/e2e/marca-responsive.spec.ts` (archivo nuevo). Un `test.describe` por viewport, 360×640 y 375×812 (`isMobile: true`, `hasTouch: true`) y 1280×800, cada uno con su `test.use`. Adentro, un loop sobre `RUTAS`: carga la ruta y mide **recién cuando el texto `/^API:/` está visible**, en este orden:
  - `document.documentElement.scrollWidth <= document.documentElement.clientWidth`;
  - en los viewports móviles, `clientWidth` igual al ancho del viewport (360, 375). Hoy falla: sin `<meta name="viewport">` el layout móvil mide ~980 px;
  - `getComputedStyle(document.body)`: `backgroundColor === "rgb(255, 255, 255)"`, `color === "rgb(26, 26, 28)"` y `fontFamily` contiene `"DM Sans"`. Hoy falla: no hay estilos;
  - hay al menos un elemento con texto visible (sin candidatos, la negativa pasaría vacía); después, ninguno de ellos tiene `color` `rgb(203, 232, 80)`. Cuando haya superficies oscuras, este chequeo tiene que mirar el fondo efectivo, no solo el color;
  - **canario, última aserción:** `page.evaluate` agrega un `div` de 2000 px de ancho y se espera `scrollWidth > clientWidth`. Prueba que la medición detecta el desborde. Va después del chequeo de lima y del `clientWidth`; después del canario no se mide nada.
  - En cada `test.use` van solo `viewport`, `isMobile` y `hasTouch`, sin spread de `devices[...]`: trae `defaultBrowserType: "webkit"` y el único proyecto es chromium. Nada se fija en `playwright.config.ts`.
- `frontend/src/marca.test.ts` (archivo nuevo, Vitest), solo lo estático:
  - `tokens.css` (vía `?raw`) define en `:root` las seis variables: los cuatro `--color-*` con sus hex, `--fuente-titulos` con Poppins y `--fuente-texto` con DM Sans;
  - `index.html` (vía `?raw`) tiene el meta viewport, los `preconnect` a `fonts.googleapis.com` y `fonts.gstatic.com` y los `<link>` de Poppins y DM Sans con `display=swap`;
  - la regla de `h1`–`h6` existe en `src/tokens.css` y usa `var(--fuente-titulos)`;
  - **hex prohibidos:** con esta llamada exacta:
    `import.meta.glob(["./**/*.{ts,tsx,css}", "!./tokens.css", "!./marca.test.ts"], { query: "?raw", import: "default", eager: true })`.
    Antes de la aserción negativa, el test verifica `expect(Object.keys(archivos)).toContain("./App.tsx")`, que `main.tsx` importa `./tokens.css` (`expect(archivos["./main.tsx"]).toMatch(/import\s+["']\.\/tokens\.css["']/)`) y que cada valor sea un string no vacío. Hoy no hay otro `.css` en `src/`, y sin `css.include` un CSS llegaría vacío y la negativa pasaría igual.
    Después, ningún archivo matchea `/#(cbe850|1a1a1c|fff(fff)?|9b9999)\b/i` (cubre `#fff` corto).
  - Hoy falla: `tokens.css` no existe y `index.html` no tiene ni meta ni fuentes. El test de hex falla por el import de `./tokens.css` que falta en `main.tsx`, no por la negativa (hoy no hay hex). Son 5 rojos en Vitest.

**Qué nace verde (y está bien):** el caso de 1280×800 en layout, la aserción de scroll sola en 360×640 y en 1280×800, la aserción de que hay al menos un elemento con texto visible, el chequeo de lima (hoy no hay color) y el canario. En 375×812 el scroll nace ROJO (981 > 980): sin meta viewport el layout de 980 px desborda un píxel. El test no lleva tolerancia. El rojo vive en el `clientWidth` móvil, en los estilos computados del `body` y en `marca.test.ts`. El canario es el que prueba que la aserción de scroll no es decorativa.

## Dónde corre el e2e
El e2e de esta spec corre en `e2e.yml` contra Railway, después del deploy, junto a `health.spec.ts`. No hay corrida local que cierre el criterio. `/^API:/` matchea también "API: error", así que el layout se mide aunque `/health` falle.

## Criterios de aceptación
- [x] `frontend/src/tokens.css` existe, define en `:root` las seis variables y se importa en `main.tsx`.
- [x] `index.html` tiene el `<meta name="viewport">`, los `preconnect` a `fonts.googleapis.com` y `fonts.gstatic.com` y los `<link>` de Poppins y DM Sans con `display=swap`.
- [x] `vite.config.ts` tiene `test.css: { include: [/\?raw/] }`.
- [ ] `marca-responsive.spec.ts` pasa en los tres viewports, con el canario, en `e2e.yml` contra Railway después del deploy: eso prueba lo que Railway sirve de verdad. Antes del cambio falló en los móviles.
- [x] `marca.test.ts` pasa; antes del cambio falló.
- [x] `npm test` sigue verde; `playwright.config.ts`, `health.spec.ts` y `package.json` sin cambios.
- [x] `docs/decisiones.md` tiene la fila de la regla responsive (2026-10-17).

## Fuera del alcance
- Mecanismo de i18n (librería, archivos de mensajes, selector de idioma). Este slice no agrega texto; el mecanismo nace con el primer slice que lo necesite.
- Título visible en la página de health.
- `docs/arquitectura-frontend.md`: lo crea la 013 (T033).
- Componentes de UI (botones, tablas, tarjetas, layout de tablero): los hace cada slice con su pantalla, siguiendo la regla.
- Modo oscuro, logo de Dapta, favicon, animaciones.
- Self-hosting de las fuentes.
- Test automático de objetivos táctiles de 44 px: la página de health no tiene controles. Entra con el primer slice que tenga un botón.
- Chequeo de contraste con axe o similar: sería una dependencia nueva.
- Cambios a `playwright.config.ts`, `health.spec.ts` o `e2e.yml`.

## Decididas
1. **Tokens en Vitest:** `?raw` con `test.css: { include: [/\?raw/] }`; el uso real de los tokens se verifica en el e2e con `getComputedStyle(document.body)`.
2. **Dónde vive el test de Vitest:** archivo nuevo `src/marca.test.ts`.
3. **Rojo del e2e:** `clientWidth` igual al viewport en móvil, más el canario de 2000 px dentro del mismo e2e.
4. **Regla transversal:** fila en `docs/decisiones.md`; chequeo con la lista `RUTAS`; sube a la constitución cuando haya router.
5. **Contraste:** en el e2e, ningún texto visible en `rgb(203, 232, 80)`.
6. **Google Fonts:** aceptable para el demo, con `preconnect` y `display=swap`; lo revisa `security` en el PR.
7. **Título:** sin título visible; regla `h1`–`h6` con Poppins, asertada en Vitest.
8. **Nombres de las variables:** en español, con prefijo por tipo: `--color-acento`, `--color-oscuro`, `--color-fondo`, `--color-gris`, `--fuente-titulos`, `--fuente-texto`.

## Preguntas abiertas
Ninguna.
