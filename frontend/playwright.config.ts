import { defineConfig, devices } from "@playwright/test";

// E2E_BASE_URL la pasa e2e.yml (input base_url): sin URL pública no hay contra qué correr.
const baseURL = process.env.E2E_BASE_URL;
if (!baseURL) throw new Error("E2E_BASE_URL no definida");

export default defineConfig({
  testDir: "e2e",
  use: { baseURL },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
