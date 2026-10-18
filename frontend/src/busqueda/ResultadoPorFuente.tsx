import { useTranslation } from "react-i18next";
import { entero } from "../compartido/formato";
import type { PorFuente } from "./tipos";

const ESTADO_POR_DEFECTO = "no_disponible";
const CONOCIDOS = new Set([
  "con_resultados",
  "sin_resultados",
  "no_disponible",
  "no_soporta_criterio",
  "limite_agotado",
  "omitida_por_tope",
]);

type Props = { porFuente: PorFuente };

/** Una línea por fuente con lo que pasó al ejecutar. La API manda códigos; acá se vuelven texto (es/en). */
export default function ResultadoPorFuente({ porFuente }: Props) {
  const { t } = useTranslation();
  return (
    <section className="resultado" aria-labelledby="resultado-por-fuente">
      <h2 id="resultado-por-fuente">{t("ejecucion.titulo")}</h2>
      <ul>
        {Object.entries(porFuente).map(([clave, r]) => {
          // Un estado que este front no conoce se lee como "no disponible": mejor eso que una clave cruda.
          const estado = CONOCIDOS.has(r.estado) ? r.estado : ESTADO_POR_DEFECTO;
          const fuente = t(`fuentes.${clave}`, { defaultValue: clave });
          const detalle = t(`ejecucion.estado.${estado}`, { count: r.encontrados, n: entero(r.encontrados) });
          return (
            <li key={clave}>
              {fuente}: {detalle}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
