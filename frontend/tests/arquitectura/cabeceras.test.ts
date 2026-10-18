// @vitest-environment node
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "vitest";
import { raiz } from "./ayuda";

type Cabecera = { key: string; value: string };
type Vercel = {
  rewrites?: { source: string; destination: string }[];
  headers?: { source: string; headers: Cabecera[] }[];
};

const vercel: Vercel = JSON.parse(fs.readFileSync(path.join(raiz, "vercel.json"), "utf8"));

// Literal: vercel.json es estático, y un origen de más en connect-src es una salida de datos de más.
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "connect-src 'self' https://ouhetsbchchwsyqxwhxb.supabase.co https://api.profitdata.tech",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

function cabeceras(): Record<string, string> {
  const bloque = vercel.headers?.find((h) => h.source === "/(.*)");
  expect(bloque, "falta el bloque headers para /(.*)").toBeDefined();
  return Object.fromEntries(bloque!.headers.map((h) => [h.key.toLowerCase(), h.value]));
}

test("todas_las_rutas_llevan_la_csp_exacta", () => {
  expect(cabeceras()["content-security-policy"]).toBe(CSP);
});

test("todas_las_rutas_llevan_las_cabeceras_de_seguridad", () => {
  expect(cabeceras()).toMatchObject({
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-opener-policy": "same-origin",
  });
});

test("el_rewrite_de_la_spa_sigue_igual", () => {
  expect(vercel.rewrites).toEqual([{ source: "/(.*)", destination: "/index.html" }]);
});
