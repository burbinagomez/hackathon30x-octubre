import { pedir } from "../api/cliente";
import type { Busqueda, PaginaLeads } from "./tipos";

export const TAMANO = 25;

export const listarBusquedas = () => pedir<{ items: Busqueda[] }>("/busquedas");

export const listarLeads = (id: string, pagina: number, conContacto = false, soloIcp = false) =>
  pedir<PaginaLeads>(`/busquedas/${encodeURIComponent(id)}/leads?pagina=${pagina}&tamano=${TAMANO}${conContacto ? "&con_contacto=true" : ""}${soloIcp ? "&solo_icp=true" : ""}`);

/** Todos los leads del tenant, o los de una fuente en todas las búsquedas. */
export const listarLeadsDeFuente = (fuente: string | null, pagina: number, conContacto = false, soloIcp = false) => {
  const q = new URLSearchParams();
  if (fuente) q.set("fuente", fuente);
  q.set("pagina", String(pagina));
  q.set("tamano", String(TAMANO));
  if (conContacto) q.set("con_contacto", "true");
  if (soloIcp) q.set("solo_icp", "true");
  return pedir<PaginaLeads>(`/leads?${q.toString()}`);
};

export type EstadoEnriquecimiento = {
  en_curso: boolean;
  procesados: number;
  contactables: number;
  pendientes: number;
  total: number;
  error: string | null;
};

/** Arranca (idempotente) la búsqueda de contactos en segundo plano. Solo vuelven conteos. */
export const iniciarEnriquecimiento = (id: string) =>
  pedir<EstadoEnriquecimiento>(`/busquedas/${encodeURIComponent(id)}/enriquecer`, { metodo: "POST" });

export const estadoEnriquecimiento = (id: string) =>
  pedir<EstadoEnriquecimiento>(`/busquedas/${encodeURIComponent(id)}/enriquecimiento`);
