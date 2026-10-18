import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { entero, moneda } from "../compartido/formato";
import { obtenerTablero } from "./api";
import type { FilaTablero, Tablero as DatosTablero } from "./tipos";

const BASICAS = ["fuente", "encontrados", "unicos"] as const;
const DE_COSTO = [
  "costo_lista", "costo_real", "desperdicio_lista", "desperdicio_real", "cpl_lista", "cpl_real", "naturales",
] as const;

function Fila({ fila, total = false, conCostos }: { fila: FilaTablero; total?: boolean; conCostos: boolean }) {
  const { t } = useTranslation();
  return (
    <tr className={total ? "total" : undefined}>
      <td>{total ? t("tablero.total") : t(`fuentes.${fila.fuente}`)}</td>
      <td>{entero(fila.encontrados)}</td>
      <td>{entero(fila.unicos)}</td>
      {conCostos && (
        <>
      <td>{moneda(fila.costo_lista)}</td>
      <td>{moneda(fila.costo_real)}</td>
      <td>{moneda(fila.desperdicio_lista)}</td>
      <td>{moneda(fila.desperdicio_real)}</td>
      <td>{moneda(fila.cpl_lista)}</td>
      <td>{moneda(fila.cpl_real)}</td>
      <td>{total ? "" : fila.cuenta_naturales ? entero(fila.naturales_no_contactables) : t("tablero.no_aplica")}</td>
        </>
      )}
    </tr>
  );
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
  // La API del [MIN] manda null en todo lo que aún no calcula: esas columnas y secciones no se pintan.
  const conCostos = datos.total.costo_lista !== null;
  const columnas = conCostos ? [...BASICAS, ...DE_COSTO] : BASICAS;
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
          {datos.fuentes.map((f) => <Fila key={f.fuente} fila={f} conCostos={conCostos} />)}
          <Fila fila={datos.total} total conCostos={conCostos} />
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
