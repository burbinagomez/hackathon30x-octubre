// @vitest-environment node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "vitest";
import { raiz } from "./ayuda";

// Armados por partes: este archivo no se delata a sí mismo si alguien lo escanea.
// supabase-js trae el prefijo suelto (`startsWith("sb_secret_")`) para rechazar esas keys en el navegador,
// así que en el build solo cuenta el prefijo seguido de un cuerpo de key.
const SECRETOS = [new RegExp("sb_" + "secret_[A-Za-z0-9_-]+"), new RegExp("service" + "_role")];
// La publishable key es pública por diseño (constitución 2.0.0) y solo vive en web.
const VARIABLES_PERMITIDAS = ["VITE_API_URL", "VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY"];

function archivos(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const ruta = path.join(dir, e.name);
    return e.isDirectory() ? archivos(ruta) : [ruta];
  });
}

/** Archivos de `dir` que contienen un secreto; la ruta es relativa a `dir`. */
function conSecretos(dir: string): string[] {
  return archivos(dir)
    .filter((f) => {
      const texto = fs.readFileSync(f, "utf8");
      return SECRETOS.some((re) => re.test(texto));
    })
    .map((f) => path.relative(dir, f));
}

test("el_detector_encuentra_un_secreto_plantado", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "zenlo-secretos-"));
  try {
    fs.writeFileSync(path.join(tmp, "limpio.ts"), "export const a = 1;\n");
    fs.writeFileSync(path.join(tmp, "malo.ts"), `export const k = "${"sb_" + "secret_x"}";\n`);
    fs.writeFileSync(path.join(tmp, "malo.js"), `const r = "${"service" + "_role"}";\n`);
    // Control positivo: el prefijo suelto, como lo usa supabase-js, no es una key.
    fs.writeFileSync(path.join(tmp, "lib.js"), `s.startsWith("${"sb_" + "secret_"}")\n`);
    expect(conSecretos(tmp).sort()).toEqual(["malo.js", "malo.ts"]);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("src_no_contiene_secretos", () => {
  const src = path.join(raiz, "src");
  // Sin esto, un src vacío o mal resuelto pasaría.
  expect(archivos(src).length).toBeGreaterThan(10);
  expect(conSecretos(src)).toEqual([]);
});

test("el_build_no_contiene_secretos", () => {
  const dist = path.join(raiz, "dist");
  // dist/ existe solo tras `npm run build`; CI lo corre antes de los tests de este archivo.
  if (!fs.existsSync(dist)) return;
  expect(conSecretos(dist)).toEqual([]);
});

test("src_solo_lee_variables_vite_permitidas", () => {
  const usadas = new Set<string>();
  for (const f of archivos(path.join(raiz, "src")).filter((f) => /\.tsx?$/.test(f))) {
    for (const m of fs.readFileSync(f, "utf8").matchAll(/import\.meta\.env\.(\w+)/g)) usadas.add(m[1]);
  }
  expect([...usadas].filter((v) => !VARIABLES_PERMITIDAS.includes(v))).toEqual([]);
  // La key de Supabase se lee del entorno y no se escribe en el código.
  expect([...usadas]).toContain("VITE_SUPABASE_PUBLISHABLE_KEY");
});
