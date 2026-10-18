import { useTranslation } from "react-i18next";
import { entero, moneda, monedaFina } from "../compartido/formato";
import type { VistaPrevia } from "./tipos";

type Props = { vista: VistaPrevia; tope: number };

export default function ResultadoVistaPrevia({ vista, tope }: Props) {
  const { t } = useTranslation();
  return (
    <section className="resultado">
      <p className="nota">{t("busqueda.conteo_antes_de_filtros")}</p>
      {vista.fuentes.length === 0 && <p>{t("busqueda.ninguna_fuente_cubre")}</p>}
      {/* Una fila por fuente: nombre | conteo | lo que no filtra. "Sin conteo" va corto y se explica una vez abajo. */}
      <ul className="fuentes-vista">
        {vista.fuentes.map((f) => (
          <li key={f.fuente} className="fila-fuente">
            <span className="fila-fuente-nombre">{t(`fuentes.${f.fuente}`)}</span>
            <span>
              {f.conteo !== null ? entero(f.conteo) : f.motivo === "sin_conteo" ? t("busqueda.sin_conteo_corto") : t(`motivos.${f.motivo}`)}
            </span>
            {f.ignorados.length > 0 && (
              <span className="fila-fuente-ignora">
                {t("busqueda.ignorados", { lista: f.ignorados.map((k) => t(`criterios.${k}`)).join(", ") })}
              </span>
            )}
          </li>
        ))}
      </ul>
      {vista.fuentes.some((f) => f.conteo === null && f.motivo === "sin_conteo") && (
        <p className="nota">{t("motivos.sin_conteo")}</p>
      )}
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
          <div className="metricas-vista">
            <p className="metrica">{t("busqueda.costo_maximo", { monto: monedaFina(vista.costo_maximo_usd) })}</p>
            <p className="metrica">{t("busqueda.tope_linea", { monto: monedaFina(tope) })}</p>
            {vista.dentro_del_tope !== null && (
              <p role="status" className="metrica">
                {t(vista.dentro_del_tope ? "busqueda.dentro_del_tope" : "busqueda.fuera_del_tope")}
              </p>
            )}
          </div>
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
