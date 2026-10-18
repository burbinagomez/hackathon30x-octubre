import { expect, test } from "@playwright/test";

test("la URL pública muestra DB: ok", async ({ page }) => {
  await page.goto("/salud");
  await expect(page.getByText("API: ok · DB: ok")).toBeVisible();
});
