import { useTranslation } from "react-i18next";
import { FLECHA_EXTERNA } from "./formato";

export type Atribucion = { fuente: string; texto: string; url: string };

/** Pie con las licencias de las fuentes presentes. Externas por exigencia de la licencia: se rotulan "Licencia ↗". */
export default function Atribuciones({ atribuciones }: { atribuciones: Atribucion[] }) {
  const { t } = useTranslation();
  if (atribuciones.length === 0) return null;
  return (
    <footer aria-label={t("tablero.atribucion")}>
      {atribuciones.map((a) => (
        <p key={a.fuente}>
          <span className="etiqueta-licencia">{t("tablero.licencia")}</span>{" "}
          <a href={a.url} target="_blank" rel="noreferrer">
            {a.texto}
            <span aria-hidden="true"> {FLECHA_EXTERNA}</span>
          </a>
        </p>
      ))}
    </footer>
  );
}
