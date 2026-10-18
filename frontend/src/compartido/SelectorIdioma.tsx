import { useTranslation } from "react-i18next";
import { pedir } from "../api/cliente";
import { fijarIdiomaUsuario, leerSesion, type IdiomaGuardado } from "../api/sesion";

const IDIOMAS: IdiomaGuardado[] = ["es", "en"];

export default function SelectorIdioma() {
  const { t, i18n } = useTranslation();

  function elegir(idioma: IdiomaGuardado) {
    void i18n.changeLanguage(idioma);
    // Sin sesión (pantalla de login) solo cambia la pestaña: no hay usuario a quien guardárselo.
    if (!leerSesion().token) return;
    fijarIdiomaUsuario(idioma);
    // ponytail: si el PATCH falla, la UI queda en el idioma elegido y el próximo login vuelve al guardado.
    pedir("/usuarios/me", { metodo: "PATCH", cuerpo: { idioma } }).catch(() => undefined);
  }

  return (
    <select
      aria-label={t("idioma.etiqueta")}
      value={i18n.language}
      onChange={(e) => elegir(e.target.value as IdiomaGuardado)}
    >
      {IDIOMAS.map((idioma) => (
        <option key={idioma} value={idioma}>
          {t(`idioma.${idioma}`)}
        </option>
      ))}
    </select>
  );
}
