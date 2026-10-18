import { expect, test, type Page } from "@playwright/test";

// Cada slice con UI suma acá sus rutas (regla responsive, docs/decisiones.md).
// `listo` es el elemento propio de la pantalla que se espera antes de medir; "/" espera el /^API:/ de health.
const RUTAS = [
  { ruta: "/", listo: (page: Page) => page.getByText(/^API:/) },
  { ruta: "/login", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { ruta: "/busqueda/nueva", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { ruta: "/tablero", listo: (page: Page) => page.getByRole("heading", { level: 1 }) },
];

// Sin spread de devices[...]: traen defaultBrowserType "webkit" y el único proyecto es chromium.
const VIEWPORTS = [
  { nombre: "360x640", viewport: { width: 360, height: 640 }, isMobile: true, hasTouch: true },
  { nombre: "375x812", viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true },
  { nombre: "1280x800", viewport: { width: 1280, height: 800 }, isMobile: false, hasTouch: false },
];

const LIMA = "rgb(203, 232, 80)";

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

        // Mira solo el color, porque hoy todo es fondo blanco; cuando haya superficies oscuras, tiene que mirar el fondo efectivo.
        const colores = await page.evaluate(() =>
          Array.from(document.body.querySelectorAll("*"))
            .filter(
              (el) =>
                Array.from(el.childNodes).some(
                  (n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim(),
                ) && el.checkVisibility(),
            )
            .map((el) => ({ tag: el.tagName, color: getComputedStyle(el).color })),
        );
        // Sin candidatos, la negativa pasaría vacía.
        expect.soft(colores.length, "elementos con texto visible").toBeGreaterThan(0);
        const enLima = colores.filter((c) => c.color === LIMA).map((c) => c.tag);
        expect.soft(enLima, "texto en lima").toEqual([]);

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
