import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { entero, moneda } from "../compartido/formato";
import { obtenerTablero } from "./api";
import type { FilaTablero, Tablero as DatosTablero } from "./tipos";

const COLUMNAS = [
  "fuente", "encontrados", "unicos", "costo_lista", "costo_real",
  "desperdicio_lista", "desperdicio_real", "cpl_lista", "cpl_real", "naturales",
] as const;

function Fila({ fila, total = false }: { fila: FilaTablero; total?: boolean }) {
  const { t } = useTranslation();
  return (
    <tr>
      <td>{total ? t("tablero.total") : t(`fuentes.${fila.fuente}`)}</td>
      <td>{entero(fila.encontrados)}</td>
      <td>{entero(fila.unicos)}</td>
      <td>{moneda(fila.costo_lista)}</td>
      <td>{moneda(fila.costo_real)}</td>
      <td>{moneda(fila.desperdicio_lista)}</td>
      <td>{moneda(fila.desperdicio_real)}</td>
      <td>{moneda(fila.cpl_lista)}</td>
      <td>{moneda(fila.cpl_real)}</td>
      <td>{total ? "" : fila.cuenta_naturales ? entero(fila.naturales_no_contactables) : t("tablero.no_aplica")}</td>
    </tr>
  );
}

export default function Tablero() {
  const { t } = useTranslation();
  const [datos, setDatos] = useState<DatosTablero | null>(null);

  useEffect(() => {
    obtenerTablero().then(setDatos).catch(() => undefined);
  }, []);

  if (!datos) return null;
  return (
    <main>
      <h1>{t("tablero.titulo")}</h1>
      <table>
        <thead>
          <tr>
            {COLUMNAS.map((c) => <th key={c}>{t(`tablero.${c}`)}</th>)}
          </tr>
        </thead>
        <tbody>
          {datos.fuentes.map((f) => <Fila key={f.fuente} fila={f} />)}
          <Fila fila={datos.total} total />
        </tbody>
      </table>
      <p>{t("tablero.costo_evals", { monto: moneda(datos.costo_evals) })}</p>
      <p>{t("tablero.revisiones_pendientes", { n: entero(datos.revisiones_pendientes) })}</p>
      <h2>{t("tablero.cobertura")}</h2>
      <ul>
        {datos.cobertura.map((c) => (
          <li key={c.pais}>{c.pais}: {c.fuentes.map((f) => t(`fuentes.${f}`)).join(", ")}</li>
        ))}
      </ul>
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
