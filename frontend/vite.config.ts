/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.ts",
    // e2e/ es de Playwright.
    include: ["src/**/*.test.{ts,tsx}"],
    // Sin esto, vitest vacía todo CSS y un `?raw` de tokens.css llega como "".
    css: { include: [/\?raw/] },
  },
});
