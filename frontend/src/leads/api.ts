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

// Primer toque por email (007). EMAIL_MODO=prueba manda solo a las casillas de prueba.
export type VistaEnvio = { modo: string; aprobados: number; a_enviar: number; asunto: string | null; cuerpo: string | null };
export type ContactoEnvio = { id: string; estado: string; enviado_en: string | null; respondio_en: string | null };
export type TasaCanal = { canal: string; contactados: number; respondieron: number; tasa: string | null };
const base = (id: string) => `/busquedas/${encodeURIComponent(id)}`;
export const vistaEnvio = (id: string) => pedir<VistaEnvio>(`${base(id)}/envio/vista-previa`, { metodo: "POST" });
export const enviarMensajes = (id: string) => pedir<{ enviados: number }>(`${base(id)}/envio`, { metodo: "POST" });
export const contactosDe = (id: string) => pedir<{ items: ContactoEnvio[] }>(`${base(id)}/contactos`);
export const marcarRespondio = (contacto: string) =>
  pedir<{ respondio: boolean }>(`/contactos/${encodeURIComponent(contacto)}/respondio`, { metodo: "POST" });
export const tasaRespuesta = () => pedir<{ items: TasaCanal[] }>("/contactos/tasa");
