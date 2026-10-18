export type Idioma = "es" | "en";

// Esqueleto (T034): devuelve un valor equivocado para que los rojos sean por aserción.
export function elegirIdioma(
  _languages: readonly string[],
  _idiomaUsuario: Idioma | null,
  _idiomaTenant: Idioma | null,
): Idioma {
  return "xx" as Idioma;
}
