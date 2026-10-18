import { descargar, pedir } from "../api/cliente";
import type { Cpql, Tablero } from "./tipos";

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
