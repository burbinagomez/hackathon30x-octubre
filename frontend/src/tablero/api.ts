import { descargar, pedir } from "../api/cliente";
import type { Cpql, ResumenImportacion, Tablero } from "./tipos";

export const obtenerTablero = () => pedir<Tablero>("/tablero/fuentes");
export const obtenerCpql = () => pedir<Cpql>("/calificaciones/cpql");

/** CSV de elegibles (jurídica + teléfono publicado + sin baja) para la hoja de Flow Studio de Dapta. */
export async function exportarParaDapta(): Promise<void> {
  const url = URL.createObjectURL(await descargar("/calificaciones/exportar"));
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = "leads_dapta.csv";
  enlace.click();
  URL.revokeObjectURL(url);
}

/** Sube el CSV de resultados de Dapta (cuerpo crudo text/csv, como lo pide el endpoint). */
export const importarDeDapta = (archivo: File) =>
  pedir<ResumenImportacion>("/calificaciones/importar", { metodo: "POST", csv: archivo });
