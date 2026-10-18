import { pedir } from "../api/cliente";
import type { Busqueda, PaginaLeads } from "./tipos";

export const TAMANO = 25;

export const listarBusquedas = () => pedir<{ items: Busqueda[] }>("/busquedas");

export const listarLeads = (id: string, pagina: number) =>
  pedir<PaginaLeads>(`/busquedas/${encodeURIComponent(id)}/leads?pagina=${pagina}&tamano=${TAMANO}`);
