// @vitest-environment node
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "vitest";
import { lintearEnTmp, raiz } from "./ayuda";

type Arbol = { [clave: string]: string | Arbol };

function aplanar(arbol: Arbol, prefijo = ""): Record<string, string> {
  const salida: Record<string, string> = {};
  for (const [k, v] of Object.entries(arbol)) {
    const clave = prefijo ? `${prefijo}.${k}` : k;
    if (typeof v === "string") salida[clave] = v;
    else Object.assign(salida, aplanar(v, clave));
  }
  return salida;
}

const leer = (idioma: string): Record<string, string> =>
  aplanar(JSON.parse(fs.readFileSync(path.join(raiz, `src/i18n/${idioma}.json`), "utf8")));

const reglaLiteral = (r: { messages: { ruleId: string | null }[] }) =>
  r.messages.filter((m) => m.ruleId === "i18next/no-literal-string");

test("es_y_en_tienen_las_mismas_claves", () => {
  const es = leer("es");
  const en = leer("en");
  // Sin esto, dos archivos vacíos pasarían.
  for (const clave of ["motivos.sin_mapeo_actividad", "acceso.ingresar"]) {
    expect(Object.keys(es), `falta ${clave} en es`).toContain(clave);
    expect(Object.keys(en), `falta ${clave} en en`).toContain(clave);
  }
  const faltanEnEn = Object.keys(es).filter((c) => !(c in en));
  const faltanEnEs = Object.keys(en).filter((c) => !(c in es));
  expect({ faltanEnEn, faltanEnEs }).toEqual({ faltanEnEn: [], faltanEnEs: [] });
  const vacios = [...Object.entries(es), ...Object.entries(en)].filter(([, v]) => v === "");
  expect(vacios).toEqual([]);
});

test("detecta_texto_literal_en_jsx", async () => {
  const r = await lintearEnTmp(
    "src/busqueda/Literal.tsx",
    "export const A = () => <p>Hola</p>;\n",
  );
  expect(reglaLiteral(r).length).toBeGreaterThanOrEqual(1);
});

test("detecta_texto_literal_en_atributo", async () => {
  const r = await lintearEnTmp(
    "src/busqueda/Literal.tsx",
    'export const A = () => <input placeholder="Buscar" />;\n',
  );
  expect(reglaLiteral(r).length).toBeGreaterThanOrEqual(1);
});

test("permite_texto_traducido", async () => {
  const r = await lintearEnTmp(
    "src/busqueda/Traducido.tsx",
    "const t = (k: string) => k;\nexport const A = () => <p>{t('acceso.ingresar')}</p>;\n",
  );
  expect(r.messages.filter((m) => m.severity === 2)).toEqual([]);
  expect(reglaLiteral(r)).toEqual([]);
});
