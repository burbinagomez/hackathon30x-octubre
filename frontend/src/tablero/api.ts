import { pedir } from "../api/cliente";
import type { Cpql, Tablero } from "./tipos";

export const obtenerTablero = () => pedir<Tablero>("/tablero/fuentes");
export const obtenerCpql = () => pedir<Cpql>("/calificaciones/cpql");
