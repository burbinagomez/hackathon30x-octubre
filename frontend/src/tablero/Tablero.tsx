import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { entero, moneda } from "../compartido/formato";
import { obtenerTablero } from "./api";
import type { FilaTablero, Tablero as DatosTablero } from "./tipos";

type Columna = "costo_lista" | "costo_real" | "desperdicio_lista" | "desperdicio_real" | "cpl_lista" | "cpl_real" | "naturales";

function Fila({ fila, total = false, columnas }: { fila: FilaTablero; total?: boolean; columnas: Columna[] }) {
  const { t } = useTranslation();
  const celdas: Record<Columna, string> = {
    costo_lista: moneda(fila.costo_lista),
    costo_real: moneda(fila.costo_real),
    desperdicio_lista: moneda(fila.desperdicio_lista),
    desperdicio_real: moneda(fila.desperdicio_real),
    cpl_lista: moneda(fila.cpl_lista),
    cpl_real: moneda(fila.cpl_real),
    naturales: total ? "" : fila.cuenta_naturales ? entero(fila.naturales_no_contactables) : t("tablero.no_aplica"),
  };
  return (
    <tr className={total ? "total" : undefined}>
      <td>{total ? t("tablero.total") : t(`fuentes.${fila.fuente}`)}</td>
      <td>{entero(fila.encontrados)}</td>
      <td>{entero(fila.unicos)}</td>
      {columnas.map((c) => <td key={c}>{celdas[c]}</td>)}
    </tr>
  );
}

/** Solo las columnas que la API ya calcula: lo que viene null en toda la tabla no se pinta (no hay columna de "—"). */
function columnasConDatos(d: DatosTablero): Columna[] {
  const filas = [...d.fuentes, d.total];
  const hay = (c: keyof FilaTablero) => filas.some((f) => f[c] !== null);
  const columnas: Columna[] = [];
  const conCostos = hay("costo_lista");
  if (conCostos) columnas.push("costo_lista", "costo_real");
  if (hay("desperdicio_lista")) columnas.push("desperdicio_lista", "desperdicio_real");
  if (conCostos) columnas.push("cpl_lista", "cpl_real");  // con costos, el CPL sin divisor se ve como "—"
  if (filas.some((f) => f.cuenta_naturales)) columnas.push("naturales");
  return columnas;
}

export default function Tablero() {
  const { t } = useTranslation();
  const [datos, setDatos] = useState<DatosTablero | null>(null);
  const [fallo, setFallo] = useState(false);

  useEffect(() => {
    obtenerTablero().then(setDatos).catch(() => setFallo(true));
  }, []);

  if (!datos) {
    return (
      <main className="pantalla pantalla-ancha">
        <h1>{t("tablero.titulo")}</h1>
        {fallo && <p role="alert" className="error">{t("tablero.error")}</p>}
      </main>
    );
  }
  // La API manda null en todo lo que aún no calcula: esas columnas y secciones no se pintan.
  const extra = columnasConDatos(datos);
  const columnas = ["fuente", "encontrados", "unicos", ...extra];
  return (
    <main className="pantalla pantalla-ancha">
      <h1>{t("tablero.titulo")}</h1>
      <div className="tabla-scroll">
      <table>
        <thead>
          <tr>
            {columnas.map((c) => <th key={c}>{t(`tablero.${c}`)}</th>)}
          </tr>
        </thead>
        <tbody>
          {datos.fuentes.map((f) => <Fila key={f.fuente} fila={f} columnas={extra} />)}
          <Fila fila={datos.total} total columnas={extra} />
        </tbody>
      </table>
      </div>
      {(datos.costo_evals !== null || datos.revisiones_pendientes !== null) && (
        <div className="metricas">
          {datos.costo_evals !== null && (
            <p className="metrica">{t("tablero.costo_evals", { monto: moneda(datos.costo_evals) })}</p>
          )}
          {datos.revisiones_pendientes !== null && (
            <p className="metrica">{t("tablero.revisiones_pendientes", { n: entero(datos.revisiones_pendientes) })}</p>
          )}
        </div>
      )}
      {datos.cobertura !== null && (
        <>
          <h2>{t("tablero.cobertura")}</h2>
          <ul className="lista">
            {datos.cobertura.map((c) => (
              <li key={c.pais}>{c.pais}: {c.fuentes.map((f) => t(`fuentes.${f}`)).join(", ")}</li>
            ))}
          </ul>
        </>
      )}
      {datos.atribuciones.length > 0 && (
        <footer aria-label={t("tablero.atribucion")}>
          {datos.atribuciones.map((a) => (
            <p key={a.fuente}>
              <a href={a.url} target="_blank" rel="noreferrer">{a.texto}</a>
            </p>
          ))}
        </footer>
      )}
    </main>
  );
}
