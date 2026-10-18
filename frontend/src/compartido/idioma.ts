import { leerSesion } from "../api/sesion";
import i18n from "../i18n";
import { elegirIdioma } from "../i18n/elegirIdioma";

/** Aplica el idioma que corresponde a la sesión actual (o a la ausencia de ella). */
export function aplicarIdioma(): void {
  const { idiomaUsuario, idiomaTenant } = leerSesion();
  void i18n.changeLanguage(elegirIdioma(navigator.languages, idiomaUsuario, idiomaTenant));
}
