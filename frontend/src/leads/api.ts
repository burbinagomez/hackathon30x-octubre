import { pedir } from "../api/cliente";
import type { Busqueda, PaginaLeads } from "./tipos";

export const TAMANO = 25;

export const listarBusquedas = () => pedir<{ items: Busqueda[] }>("/busquedas");

export const listarLeads = (id: string, pagina: number) =>
  pedir<PaginaLeads>(`/busquedas/${encodeURIComponent(id)}/leads?pagina=${pagina}&tamano=${TAMANO}`);

/** Todos los leads del tenant, o los de una fuente en todas las búsquedas. */
export const listarLeadsDeFuente = (fuente: string | null, pagina: number) => {
  const q = new URLSearchParams();
  if (fuente) q.set("fuente", fuente);
  q.set("pagina", String(pagina));
  q.set("tamano", String(TAMANO));
  return pedir<PaginaLeads>(`/leads?${q.toString()}`);
};
