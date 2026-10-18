// @vitest-environment node
import path from "node:path";
import { ESLint } from "eslint";
import { expect, test } from "vitest";

const raiz = path.resolve(__dirname, "../..");

// [MIN]: solo la guarda sobre el repo real. Los canarios de límites entre features
// (boundaries) entran con T036 en el Pulido.
test("el_repo_no_tiene_violaciones", async () => {
  const eslint = new ESLint({
    cwd: raiz,
    overrideConfigFile: path.join(raiz, "eslint.config.js"),
    // Con la config vacía nada matchea: que lo diga el assert de abajo, no una excepción.
    errorOnUnmatchedPattern: false,
  });
  const resultados = await eslint.lintFiles(["src"]);

  const errores = resultados.flatMap((r) =>
    r.messages
      .filter((m) => m.severity === 2)
      .map((m) => `${path.relative(raiz, r.filePath)}:${m.line} ${m.ruleId} ${m.message}`),
  );
  expect(errores).toEqual([]);

  // Si un glob no matchea o un ignores se come los .tsx, el test falla en lugar de pasar vacío.
  const archivos = resultados.map((r) => path.relative(raiz, r.filePath));
  expect(archivos).toContain("src/App.tsx");
  expect(archivos).toContain("src/busqueda/NuevaBusqueda.tsx");
});
