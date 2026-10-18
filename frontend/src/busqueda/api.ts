import { pedir } from "../api/cliente";
import type { Actividad, PedidoVistaPrevia, VistaPrevia } from "./tipos";

export const listarActividades = () => pedir<Actividad[]>("/actividades");

export const vistaPrevia = (pedido: PedidoVistaPrevia) =>
  pedir<VistaPrevia>("/busquedas/vista-previa", { metodo: "POST", cuerpo: pedido });

export const ejecutar = (id: string) =>
  pedir<unknown>(`/busquedas/${encodeURIComponent(id)}/ejecutar`, { metodo: "POST" });
