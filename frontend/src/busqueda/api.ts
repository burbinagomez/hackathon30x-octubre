import { pedir } from "../api/cliente";
import type { Actividad, GeografiaDePais, PaisesConGeografia, PedidoVistaPrevia, ResultadoEjecucion, VistaPrevia } from "./tipos";

export const listarActividades = () => pedir<Actividad[]>("/actividades");

export const listarPaises = () => pedir<PaisesConGeografia>("/geografia");

export const divisionesDe = (pais: string) =>
  pedir<GeografiaDePais>(`/geografia?pais=${encodeURIComponent(pais)}`);

export const vistaPrevia = (pedido: PedidoVistaPrevia) =>
  pedir<VistaPrevia>("/busquedas/vista-previa", { metodo: "POST", cuerpo: pedido });

export const ejecutar = (id: string) =>
  pedir<ResultadoEjecucion>(`/busquedas/${encodeURIComponent(id)}/ejecutar`, { metodo: "POST" });
