import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { navegar } from "../compartido/navegar";
import { entero, moneda, monedaFina } from "../compartido/formato";
import Trabajando from "../compartido/Trabajando";
import ResultadoPorFuente from "./ResultadoPorFuente";
import ResultadoVistaPrevia from "./ResultadoVistaPrevia";
import type { Busqueda } from "./useBusqueda";
import type { PedidoVistaPrevia, VistaPrevia } from "./tipos";

/** Lo que la búsqueda en curso está consultando, con los números de la vista previa: nada inventado. */
function DetalleBusqueda({ vista, tope }: { vista: VistaPrevia; tope: number }) {
  const { t } = useTranslation();
  const nombre = (clave: string) => t(`fuentes.${clave}`, { defaultValue: clave });
  return (
    <>
      <ul>
        {vista.fuentes.map((f) => (
          <li key={f.fuente}>
            {f.conteo === null
              ? t("busqueda.trabajando.detalle_fuente_sin_conteo", { fuente: nombre(f.fuente) })
              : t("busqueda.trabajando.detalle_fuente", { fuente: nombre(f.fuente), conteo: entero(f.conteo) })}
            {f.ignorados.length > 0 && ` · ${t("busqueda.trabajando.detalle_ignora", { campos: f.ignorados.join(", ") })}`}
          </li>
        ))}
      </ul>
      {vista.costo_maximo_usd !== null && (
        <p>{t("busqueda.trabajando.detalle_costo", { maximo: monedaFina(vista.costo_maximo_usd), tope: moneda(tope) })}</p>
      )}
    </>
  );
}

type Props = {
  busqueda: Busqueda;
  pedido: PedidoVistaPrevia;
  tope: number;
  /** El pedido tiene lo mínimo para calcular la vista previa (actividad y tope). */
  puedeVista: boolean;
  /** Botón extra en la misma fila (el chat pone "Editar en Filtros" entre Vista previa y Buscar). */
  extra?: ReactNode;
  /** Buscar es el botón primario. El chat lo apaga cuando falta la actividad y lo primario es editar. */
  buscarPrimario?: boolean;
};

/** Vista previa, Buscar, píldora de espera y resultado por fuente. Fragmento: los hijos caen en la grilla de quien lo monta. */
export default function BloqueBusqueda({ busqueda, pedido, tope, puedeVista, extra, buscarPrimario = true }: Props) {
  const { t } = useTranslation();
  const { vista, resultado, ocupado, fallo } = busqueda;
  const puedeBuscar = resultado === null && vista !== null && vista.dentro_del_tope !== false && vista.fuentes.length > 0;
  return (
    <>
      {ocupado === "vista" && <Trabajando texto={t("busqueda.trabajando.vista_previa")} />}
      {vista && <ResultadoVistaPrevia vista={vista} tope={tope} />}
      <div className="acciones acciones-fin">
        <button type="button" className="boton" disabled={!puedeVista || ocupado !== null} aria-busy={ocupado === "vista"}
          onClick={() => busqueda.previsualizar(pedido)}>
          {t("busqueda.vista_previa")}
        </button>
        {extra}
        <button type="button" className={buscarPrimario ? "boton boton-primario" : "boton"}
          disabled={!puedeBuscar || ocupado !== null} aria-busy={ocupado === "buscar"} onClick={busqueda.buscar}>
          {ocupado === "buscar" && <span className="anillo anillo-chico" aria-hidden="true" />}
          {ocupado === "buscar" ? t("busqueda.trabajando.buscando_boton") : t("busqueda.buscar")}
        </button>
      </div>
      {ocupado === "buscar" && vista && (
        // La API responde todo junto al final: mientras tanto se ve qué fuentes se están consultando.
        <Trabajando
          flotante
          texto={t("busqueda.trabajando.buscando")}
          pasos={vista.fuentes.map((f) => t("busqueda.trabajando.consultando", { fuente: t(`fuentes.${f.fuente}`, { defaultValue: f.fuente }) }))}
          detalle={<DetalleBusqueda vista={vista} tope={tope} />}
        />
      )}
      {resultado && (
        <>
          <ResultadoPorFuente porFuente={resultado.por_fuente} />
          {resultado.estado === "error" && <p role="status">{t("ejecucion.ninguna_respondio")}</p>}
          <div className="acciones">
            <button type="button" className="boton" onClick={() => navegar("/tablero")}>
              {t("ejecucion.ver_tablero")}
            </button>
          </div>
        </>
      )}
      {fallo && <p role="alert" className="error">{t("busqueda.error")}</p>}
    </>
  );
}
