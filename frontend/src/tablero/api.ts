import { pedir } from "../api/cliente";
import type { Tablero } from "./tipos";

export const obtenerTablero = () => pedir<Tablero>("/tablero/fuentes");
