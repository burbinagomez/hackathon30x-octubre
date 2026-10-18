import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Enlace from "../compartido/Enlace";
import Esqueleto from "../compartido/Esqueleto";
import { entero, monedaFina } from "../compartido/formato";
import { RUTA_COSTOS } from "../compartido/rutas";
import { listarCostos } from "./api";
import type { PaginaCostos } from "./tipos";

const UNIDADES: Record<string, string> = {
  socrata_descarga: "segundos", overpass_query: "segundos", web_fetch: "segundos", croma_consulta: "creditos",
  llm_tokens_in: "tokens", llm_tokens_out: "tokens", jev_tokens: "tokens",
};
const COLUMNAS = ["ts", "tipo", "fuente", "proveedor", "cantidad", "costo", "gratis", "lead"] as const;

type Props = { busquedaId: string | null };

/** Libro de costos, solo lectura: totales arriba (general, por tipo, por fuente) y las operaciones abajo, paginadas. */
export default function Costos({ busquedaId }: Props) {
  const { t, i18n } = useTranslation();
  const [pagina, setPagina] = useState(1);
  const [datos, setDatos] = useState<PaginaCostos | null>(null);
  const [fallo, setFallo] = useState(false);

  useEffect(() => {
    setFallo(false);
    listarCostos(pagina, busquedaId).then(setDatos).catch(() => setFallo(true));
  }, [pagina, busquedaId]);

  const titulo = <h1>{t("costos.titulo")}</h1>;
  if (!datos) {
    return (
      <main className="pantalla pantalla-ancha">
        {titulo}
        {fallo ? <p role="alert" className="error">{t("costos.error")}</p> : <Esqueleto filas={6} />}
      </main>
    );
  }

  const paginas = Math.max(1, Math.ceil(datos.total / datos.tamano));
  // Cada tipo cobra en su unidad: segundos de cómputo, créditos de Croma o tokens.
  const cantidad = (tipo: string, valor: string) => {
    const n = Number(valor);
    const numero = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 3 }).format(n);
    const unidad = UNIDADES[tipo];
    return unidad ? `${numero} ${t(`costos.unidad.${unidad}`, { count: n })}` : numero;
  };
  const fecha = (iso: string) => new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "medium" }).format(new Date(iso));
  const sino = (v: boolean) => (v ? t("costos.si") : t("costos.no"));
  const tipo = (k: string) => t(`costos.tipos.${k}`, { defaultValue: k });
  const fuente = (k: string | null) => (k ? t(`fuentes.${k}`, { defaultValue: k }) : t("fuentes.sin_atribuir"));

  return (
    <main className="pantalla pantalla-ancha">
      {titulo}
      {fallo && <p role="alert" className="error">{t("costos.error")}</p>}
      {busquedaId && (
        <p className="nota">
          {t("costos.filtrado")} <Enlace a={RUTA_COSTOS}>{t("costos.ver_todo")}</Enlace>
        </p>
      )}
      <div className="metricas">
        <p className="metrica">
          {t("costos.total")}: <strong data-testid="total-usd">{monedaFina(datos.total_usd)}</strong>
        </p>
        <p className="metrica">
          {t("costos.total_real")}: <strong data-testid="total-real-usd">{monedaFina(datos.total_real_usd)}</strong>
        </p>
      </div>
      <div className="subtotales">
        <section aria-labelledby="costos-por-tipo">
          <h2 id="costos-por-tipo">{t("costos.por_tipo")}</h2>
          <ul className="lista">
            {datos.por_tipo.map((s) => <li key={s.tipo}><span>{tipo(s.tipo)}</span> <span>{monedaFina(s.costo_usd)}</span></li>)}
          </ul>
        </section>
        <section aria-labelledby="costos-por-fuente">
          <h2 id="costos-por-fuente">{t("costos.por_fuente")}</h2>
          <ul className="lista">
            {datos.por_fuente.map((s) => <li key={s.fuente}><span>{fuente(s.fuente)}</span> <span>{monedaFina(s.costo_usd)}</span></li>)}
          </ul>
        </section>
      </div>
      {datos.items.length === 0 && <p>{t("costos.vacio")}</p>}
      {datos.items.length > 0 && (
        <>
          <p className="nota">{t("costos.operaciones", { total: entero(datos.total) })}</p>
          <div className="tabla-scroll">
            <table className="tabla-costos" aria-label={t("costos.tabla")}>
              <thead>
                <tr>
                  {COLUMNAS.map((c) => (
                    <th key={c}>{t(`costos.col.${c}`)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {datos.items.map((f, i) => (
                  <tr key={`${f.ts}-${i}`}>
                    <td>{fecha(f.ts)}</td>
                    <td>{tipo(f.tipo)}</td>
                    <td>{fuente(f.fuente)}</td>
                    <td>{f.proveedor}</td>
                    <td>{cantidad(f.tipo, f.cantidad)}</td>
                    <td>{monedaFina(f.costo_usd)}</td>
                    <td>{sino(f.gratis)}</td>
                    <td>{sino(f.lead)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="paginacion" aria-label={t("costos.tabla")}>
            <button type="button" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>{t("costos.anterior")}</button>
            <span>{t("costos.pagina_de", { pagina: datos.pagina, paginas })}</span>
            <button type="button" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>{t("costos.siguiente")}</button>
          </nav>
        </>
      )}
    </main>
  );
}
