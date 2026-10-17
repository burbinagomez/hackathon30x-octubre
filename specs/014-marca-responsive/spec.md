# Spec 014 — Marca Dapta y responsive

**Slice:** 014 · **Rama:** `feature/014-marca-responsive` · **Tiempo:** ≤ 1,5 h
**Depende de:** 001 (front con la página de health). **Desbloquea:** todo slice con UI (005, 007, 008, 010…), que hereda los tokens y la regla responsive.

## Para quién
- **El jurado y la audiencia de Dapta:** el demo se ve como un producto de Dapta, también en el celular de quien lo mira.
- **El equipo:** los slices con UI arrancan con tokens, tipografía y una regla responsive ya escrita y con su test, en vez de decidir colores y breakpoints cada uno.

## Qué hace
- **Tokens** de Dapta como variables CSS en `:root`, en `frontend/src/tokens.css`: acento `#CBE850`, oscuro `#1A1A1C`, fondo `#FFFFFF`, gris `#9B9999`. Ningún componente escribe estos hex a mano: usa la variable.
- **Tipografía:** Poppins para títulos, DM Sans para texto, cargadas desde Google Fonts con `<link>` en `frontend/index.html`.
- **Viewport:** `index.html` suma `<meta name="viewport" content="width=device-width, initial-scale=1">`. Sin esa línea, un navegador móvil dibuja la página en un layout de ~980 px y el test de 375 px no mide lo que debe.
- **Contraste:** el lima nunca va como color de texto sobre blanco (no llega a contraste legible). Va de fondo con texto `#1A1A1C` encima, o como texto/acento sobre el oscuro.
- La página de health aplica los tokens y las fuentes. El texto visible no cambia ("API: ok · DB: ok"): `App.test.tsx` y `e2e/health.spec.ts` siguen pasando sin tocarlos.

## Regla transversal: responsive en todo slice con UI
Vale para este slice y para todos los siguientes que toquen UI. Cada uno la cumple en su propio PR:
1. **Mobile-first:** estilos base para móvil; `min-width` en media queries para crecer.
2. **Mínimo 360 px** de ancho sin romper el layout.
3. **Sin scroll horizontal** de la página: `document.documentElement.scrollWidth <= clientWidth`.
4. **Objetivos táctiles de al menos 44 × 44 px** (botones, links, controles).
5. **Tablas en móvil:** pasan a tarjetas, o hacen scroll horizontal dentro de su propio contenedor (`overflow-x: auto`), nunca de la página.
6. Cada slice con UI agrega sus pantallas al e2e de esta spec (o a uno igual) en 375×812 y 1280×800.

## Restricciones
- **Sin Tailwind ni dependencias nuevas.** CSS plano; `package.json` no cambia.
- **Idiomas es/en:** la UI sigue existiendo en los dos idiomas. Este slice no agrega texto visible nuevo.
- **No se modifican** `frontend/playwright.config.ts` ni `frontend/e2e/health.spec.ts`: los usa `e2e.yml` para T032.

## Terminado cuando (tests que hoy fallan)
- `frontend/e2e/marca-responsive.spec.ts` (archivo nuevo) → en dos viewports, 375×812 (móvil, `isMobile: true`) y 1280×800, cargando `/`:
  - `document.documentElement.scrollWidth <= document.documentElement.clientWidth`;
  - en 375×812, `clientWidth === 375`. Hoy falla: sin `<meta name="viewport">`, el layout móvil mide ~980 px. Esta aserción es la que pone el test en rojo; la de scroll sola nace verde con la página actual (ver preguntas abiertas).
  - El viewport se fija con `test.use(...)` dentro del archivo, no en `playwright.config.ts`.
- Test de Vitest → la página de health usa los tokens (fondo, texto, fuente). Hoy falla: `tokens.css` no existe. **Cómo se asierta está abierto** (ver preguntas abiertas).

## Cómo se corre el e2e local
```bash
cd frontend && npm run build && npx vite preview --port 4173 &
E2E_BASE_URL=http://localhost:4173 npx playwright test e2e/marca-responsive.spec.ts
```
Solo ese archivo: `health.spec.ts` contra `vite preview` falla porque no hay API detrás. Sin API, la página muestra "API: error · DB: error", y para medir el layout alcanza. En `e2e.yml`, el archivo nuevo corre también contra Railway, junto a `health.spec.ts`.

## Criterios de aceptación
- [ ] `frontend/src/tokens.css` existe y define en `:root` las cuatro variables con los hex de arriba.
- [ ] `index.html` tiene el `<meta name="viewport">` y los `<link>` a Google Fonts de Poppins y DM Sans.
- [ ] Ningún archivo de `frontend/src/` fuera de `tokens.css` contiene `#CBE850`, `#1A1A1C`, `#FFFFFF` ni `#9B9999` (sin distinguir mayúsculas).
- [ ] Ningún texto se pinta en lima sobre fondo blanco.
- [ ] `marca-responsive.spec.ts` pasa en los dos viewports; antes del cambio falló en 375×812.
- [ ] El test de Vitest de tokens pasa; antes del cambio falló.
- [ ] `npm test` sigue verde; `playwright.config.ts`, `health.spec.ts` y `package.json` sin cambios.
- [ ] La regla transversal queda escrita en `docs/arquitectura-frontend.md` (lo pide el principio X; el archivo hoy no existe y nace en este slice).

## Fuera del alcance
- Mecanismo de i18n (librería, archivos de mensajes, selector de idioma). Este slice no agrega texto; el mecanismo nace con el primer slice que lo necesite.
- Componentes de UI (botones, tablas, tarjetas, layout de tablero): los hace cada slice con su pantalla, siguiendo la regla.
- Modo oscuro, logo de Dapta, favicon, animaciones.
- Self-hosting de las fuentes (se cargan de Google Fonts).
- Test automático de objetivos táctiles de 44 px: la página de health no tiene controles. Entra con el primer slice que tenga un botón.
- Chequeo automático de contraste (axe o similar): sería una dependencia nueva.
- Cambios a `playwright.config.ts`, `health.spec.ts` o `e2e.yml`.

## Preguntas abiertas
1. **Cómo asertar en Vitest que un elemento usa un token.** jsdom no aplica hojas de estilo importadas (Vitest no procesa CSS por defecto) ni resuelve `var(--x)` en `getComputedStyle`. Opciones sin decidir: leer `tokens.css` como texto y verificar las variables; verificar que el elemento usa una clase o `style` con `var(--…)`; activar `css` en la config de Vitest. Lo decide el advisor antes del test rojo.
2. **¿Dónde vive el test de Vitest?** ¿Dentro de `App.test.tsx` o en un archivo nuevo (`src/tokens.test.ts`)?
3. **La aserción de scroll nace verde.** Con la página actual (un `div` con texto corto), `scrollWidth <= clientWidth` pasa hoy en los dos viewports. El rojo lo da `clientWidth === 375`. ¿Alcanza, o el e2e agrega un caso que hoy desborde?
4. **La regla transversal no tiene chequeo automático general.** La constitución pide que toda regla tenga uno. Hoy el chequeo es el e2e por pantalla, que cada slice tiene que acordarse de extender. ¿Va a la constitución (con qué chequeo), a `docs/arquitectura-frontend.md` o a `CLAUDE.md`?
5. **¿El contraste se verifica en el e2e?** Por ejemplo, que ningún elemento con texto visible tenga `color` `rgb(203, 232, 80)` sobre fondo blanco. No está pedido; queda a decisión.
6. **Google Fonts y privacidad.** Cargar desde Google le pasa a Google la IP de cada visitante. Para un demo parece aceptable; si `security` lo objeta, se pasa a self-hosting (fuera de alcance acá).
7. **¿Qué se ve en "título"?** La página de health no tiene título visible. ¿Se agrega uno (con es/en) para que Poppins tenga dónde aplicarse, o Poppins queda solo definida para los slices siguientes?
