import { expect, test } from "vitest";
import { elegirIdioma, type Idioma } from "./elegirIdioma";

type Caso = [string, string[], Idioma | null, Idioma | null, Idioma];

const casos: Caso[] = [
  ["la elección guardada gana sobre navegador y tenant", ["es-CO"], "en", "es", "en"],
  ["el navegador gana sobre el tenant", ["es-CO"], null, "en", "es"],
  ["sin navegador útil vale el tenant", ["fr"], null, "en", "en"],
  ["sin nada es es", ["fr"], null, null, "es"],
  ["corta el código regional y toma el primero que esté en {es, en}", ["pt-BR", "en-US"], null, null, "en"],
];

test.each(casos)("precedencia: %s", (_nombre, languages, usuario, tenant, esperado) => {
  expect(elegirIdioma(languages, usuario, tenant)).toBe(esperado);
});
