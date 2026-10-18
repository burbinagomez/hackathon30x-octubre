import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
    // e2e/ es de Playwright.
    exclude: ["e2e/**", "node_modules/**"],
    // Sin esto, vitest vacía todo CSS y un `?raw` de tokens.css llega como "".
    css: { include: [/\?raw/] },
  },
});
