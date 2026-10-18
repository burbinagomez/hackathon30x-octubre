import { useTranslation } from "react-i18next";

/** Barras que brillan mientras llega una tabla o una lista: la pantalla no queda en blanco. */
export default function Esqueleto({ filas = 4 }: { filas?: number }) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-busy="true" aria-live="polite">
      <span className="solo-lector">{t("comun.cargando")}</span>
      {Array.from({ length: filas }, (_, i) => <div key={i} className="esqueleto" aria-hidden="true" />)}
    </div>
  );
}
