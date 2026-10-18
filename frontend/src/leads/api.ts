import { pedir } from "../api/cliente";
import type { Busqueda, PaginaLeads } from "./tipos";

export const TAMANO = 25;

export const listarBusquedas = () => pedir<{ items: Busqueda[] }>("/busquedas");

export const listarLeads = (id: string, pagina: number, conContacto = false) =>
  pedir<PaginaLeads>(`/busquedas/${encodeURIComponent(id)}/leads?pagina=${pagina}&tamano=${TAMANO}${conContacto ? "&con_contacto=true" : ""}`);

/** Todos los leads del tenant, o los de una fuente en todas las búsquedas. */
export const listarLeadsDeFuente = (fuente: string | null, pagina: number, conContacto = false) => {
  const q = new URLSearchParams();
  if (fuente) q.set("fuente", fuente);
  q.set("pagina", String(pagina));
  q.set("tamano", String(TAMANO));
  if (conContacto) q.set("con_contacto", "true");
  return pedir<PaginaLeads>(`/leads?${q.toString()}`);
};

export type ResumenEnriquecimiento = {
  procesados: number;
  contactables: number;
  clasificados: number;
  sin_clasificar: number;
  cortado: boolean;
  pendientes: number;
};

/** Una tanda de enriquecimiento (sitio web, RUES, jev) para los leads de la búsqueda. Solo vuelven conteos. */
export const enriquecer = (id: string) =>
  pedir<ResumenEnriquecimiento>(`/busquedas/${encodeURIComponent(id)}/enriquecer`, { metodo: "POST" });
