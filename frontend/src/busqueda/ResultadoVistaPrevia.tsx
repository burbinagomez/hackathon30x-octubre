import { useTranslation } from "react-i18next";
import { entero, moneda } from "../compartido/formato";
import type { VistaPrevia } from "./tipos";

type Props = { vista: VistaPrevia; tope: number };

export default function ResultadoVistaPrevia({ vista, tope }: Props) {
  const { t } = useTranslation();
  return (
    <section className="resultado">
      <p className="nota">{t("busqueda.conteo_antes_de_filtros")}</p>
      {vista.fuentes.length === 0 && <p>{t("busqueda.ninguna_fuente_cubre")}</p>}
      <ul>
        {vista.fuentes.map((f) => (
          <li key={f.fuente}>
            {t(`fuentes.${f.fuente}`)}: {f.conteo === null ? t(`motivos.${f.motivo}`) : entero(f.conteo)}
            {f.ignorados.length > 0 &&
              ` (${t("busqueda.ignorados", { lista: f.ignorados.map((k) => t(`criterios.${k}`)).join(", ") })})`}
          </li>
        ))}
      </ul>
      {vista.descartadas.length > 0 && (
        <>
          <h2>{t("busqueda.descartadas")}</h2>
          <ul>
            {vista.descartadas.map((d) => (
              <li key={d.fuente}>
                {t(`fuentes.${d.fuente}`)}: {t(`motivos.${d.motivo}`)}
              </li>
            ))}
          </ul>
        </>
      )}
      {/* null = la API no lo calcula todavía: la línea no se pinta (ni "—", ni 0). Sin costo máximo no hay tope que comparar. */}
      {vista.costo_estimado_usd !== null && (
        <p>{t("busqueda.costo_estimado", { monto: moneda(vista.costo_estimado_usd) })}</p>
      )}
      {vista.costo_maximo_usd !== null && (
        <>
          <p>{t("busqueda.costo_maximo", { monto: moneda(vista.costo_maximo_usd) })}</p>
          <p>{t("busqueda.tope_linea", { monto: moneda(tope) })}</p>
          <p className="nota">{t("busqueda.se_compara_el_maximo")}</p>
        </>
      )}
      {vista.creditos_restantes_mes !== null && (
        <p>{t("busqueda.creditos_restantes", { n: entero(vista.creditos_restantes_mes) })}</p>
      )}
      {vista.requests_restantes_24h !== null && (
        <p>{t("busqueda.requests_restantes", { n: entero(vista.requests_restantes_24h) })}</p>
      )}
    </section>
  );
}
