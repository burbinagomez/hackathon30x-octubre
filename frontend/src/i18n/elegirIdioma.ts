export type Idioma = "es" | "en";

const SOPORTADOS: readonly string[] = ["es", "en"];

/**
 * Idioma de la UI: la elección guardada, el primer idioma del navegador que esté en {es, en}
 * (cortado al código base), el del tenant, y es.
 */
export function elegirIdioma(
  languages: readonly string[],
  idiomaUsuario: Idioma | null,
  idiomaTenant: Idioma | null,
): Idioma {
  if (idiomaUsuario) return idiomaUsuario;
  for (const l of languages) {
    const base = l.split("-")[0].toLowerCase();
    if (SOPORTADOS.includes(base)) return base as Idioma;
  }
  return idiomaTenant ?? "es";
}
