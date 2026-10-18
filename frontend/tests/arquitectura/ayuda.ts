import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { ESLint } from "eslint";

export const raiz = path.resolve(__dirname, "../..");

/** Lintea un solo archivo en un directorio temporal, con la config REAL del repo. */
export async function lintearEnTmp(archivo: string, contenido: string) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "zenlo-lint-"));
  try {
    const destino = path.join(tmp, archivo);
    fs.mkdirSync(path.dirname(destino), { recursive: true });
    fs.writeFileSync(destino, contenido);
    const eslint = new ESLint({
      cwd: tmp,
      overrideConfigFile: path.join(raiz, "eslint.config.js"),
    });
    const [resultado] = await eslint.lintFiles([archivo]);
    return resultado;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}
