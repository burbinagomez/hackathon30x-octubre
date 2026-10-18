import { expect, test, type Page } from "@playwright/test";

// Cada slice con UI suma acá sus rutas (regla responsive, docs/decisiones.md).
// `listo` es el elemento propio de la pantalla que se espera antes de medir; "/" espera el /^API:/ de health.
const RUTAS = [
  { ruta: "/", listo: (page: Page) => page.getByText(/^API:/) },
  { ruta: "/login", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { ruta: "/busqueda/nueva", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { ruta: "/tablero", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { ruta: "/leads", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { ruta: "/busquedas", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { ruta: "/busquedas/11111111-1111-4111-8111-111111111111/leads", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
];

// Sin spread de devices[...]: traen defaultBrowserType "webkit" y el único proyecto es chromium.
const VIEWPORTS = [
  { nombre: "360x640", viewport: { width: 360, height: 640 }, isMobile: true, hasTouch: true },
  { nombre: "375x812", viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true },
  // El corte de 48rem: ahí el formulario pasa a dos columnas.
  { nombre: "768x1024", viewport: { width: 768, height: 1024 }, isMobile: false, hasTouch: true },
  { nombre: "1280x800", viewport: { width: 1280, height: 800 }, isMobile: false, hasTouch: false },
];

const LIMA = "rgb(203, 232, 80)";
const OSCURO = "rgb(26, 26, 28)";

/** Texto visible con su color y el fondo efectivo (primer ancestro con fondo no transparente). */
async function medirTextos(page: Page) {
  return page.evaluate(() => {
    const fondoDe = (el: Element): string => {
      for (let n: Element | null = el; n; n = n.parentElement) {
        const f = getComputedStyle(n).backgroundColor;
        if (f !== "rgba(0, 0, 0, 0)" && f !== "transparent") return f;
      }
      return "rgb(255, 255, 255)";
    };
    return Array.from(document.body.querySelectorAll("*"))
      .filter(
        (el) =>
          Array.from(el.childNodes).some(
            (n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim(),
          ) && el.checkVisibility(),
      )
      .map((el) => ({ tag: el.tagName, color: getComputedStyle(el).color, fondo: fondoDe(el) }));
  });
}

for (const v of VIEWPORTS) {
  test.describe(v.nombre, () => {
    test.use({ viewport: v.viewport, isMobile: v.isMobile, hasTouch: v.hasTouch });

    for (const { ruta, listo } of RUTAS) {
      test(`${ruta} respeta marca y responsive`, async ({ page }) => {
        await page.goto(ruta);
        // Medir antes de que la pantalla (o /health) conteste mediría una página a medias.
        await expect(listo(page).first()).toBeVisible();

        const medida = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          client: document.documentElement.clientWidth,
        }));
        // soft: el reporte muestra todas las aserciones que fallan, no solo la primera.
        expect.soft(medida.scroll, "sin scroll horizontal").toBeLessThanOrEqual(medida.client);
        if (v.isMobile) {
          expect.soft(medida.client, "layout móvil al ancho del viewport").toBe(v.viewport.width);
        }

        const body = await page.evaluate(() => {
          const s = getComputedStyle(document.body);
          return { fondo: s.backgroundColor, color: s.color, fuente: s.fontFamily };
        });
        expect.soft(body.fondo, "fondo del body").toBe("rgb(255, 255, 255)");
        expect.soft(body.color, "texto del body").toBe("rgb(26, 26, 28)");
        expect.soft(body.fuente, "fuente del body").toContain("DM Sans");

        // Fondo efectivo: el primer ancestro con fondo no transparente (el del body si no hay otro).
        const colores = await medirTextos(page);
        // Sin candidatos, la negativa pasaría vacía.
        expect.soft(colores.length, "elementos con texto visible").toBeGreaterThan(0);
        const enLima = colores
          .filter((c) => c.color === LIMA && c.fondo !== OSCURO)
          .map((c) => `${c.tag} sobre ${c.fondo}`);
        expect.soft(enLima, "texto en lima sobre fondo claro").toEqual([]);

        // Regla 4: objetivos táctiles de al menos 44 x 44 px (controles y links visibles).
        const chicos = await page.evaluate(() =>
          Array.from(document.querySelectorAll("button, input, select, textarea, a[href]"))
            .filter((el) => el.checkVisibility())
            .map((el) => ({ el, r: el.getBoundingClientRect() }))
            .filter(({ r }) => r.width < 44 || r.height < 44)
            .map(({ el, r }) => `${el.tagName} ${Math.round(r.width)}x${Math.round(r.height)}`),
        );
        expect.soft(chicos, "objetivos táctiles menores a 44x44").toEqual([]);

        // Canario, última aserción: prueba que la medición detecta un desborde. Después no se mide nada.
        const desborde = await page.evaluate(() => {
          const div = document.createElement("div");
          div.style.width = "2000px";
          div.style.height = "1px";
          document.body.appendChild(div);
          return {
            scroll: document.documentElement.scrollWidth,
            client: document.documentElement.clientWidth,
          };
        });
        expect(desborde.scroll, "canario de desborde").toBeGreaterThan(desborde.client);
      });
    }
  });
}

// Tema oscuro: sigue la preferencia del sistema (spec 014, enmienda 2026-10-18). 360 incluido: el formulario de Nueva búsqueda se revisa ahí en ambos temas.
for (const v of VIEWPORTS) {
  test.describe(`${v.nombre} oscuro`, () => {
    test.use({
      viewport: v.viewport,
      isMobile: v.isMobile,
      hasTouch: v.hasTouch,
      colorScheme: "dark",
    });

    for (const { ruta, listo } of RUTAS) {
      test(`${ruta} usa la marca en oscuro`, async ({ page }) => {
        await page.goto(ruta);
        await expect(listo(page).first()).toBeVisible();

        const body = await page.evaluate(() => {
          const s = getComputedStyle(document.body);
          return { fondo: s.backgroundColor, color: s.color };
        });
        expect.soft(body.fondo, "fondo del body").toBe("rgb(26, 26, 28)");
        expect.soft(body.color, "texto del body").toBe("rgb(255, 255, 255)");

        const textos = await medirTextos(page);
        expect.soft(textos.length, "elementos con texto visible").toBeGreaterThan(0);
        const iguales = textos
          .filter((t) => t.color === t.fondo)
          .map((t) => `${t.tag} ${t.color}`);
        expect.soft(iguales, "texto con el color de su fondo").toEqual([]);
        const scroll = await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        );
        expect.soft(scroll, "sin scroll horizontal").toBe(true);
      });
    }
  });
}
