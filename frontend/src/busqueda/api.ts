import { pedir } from "../api/cliente";
import type { Actividad, GeografiaDePais, PaisesConGeografia, PedidoVistaPrevia, VistaPrevia } from "./tipos";

export const listarActividades = () => pedir<Actividad[]>("/actividades");

export const listarPaises = () => pedir<PaisesConGeografia>("/geografia");

export const divisionesDe = (pais: string) =>
  pedir<GeografiaDePais>(`/geografia?pais=${encodeURIComponent(pais)}`);

export const vistaPrevia = (pedido: PedidoVistaPrevia) =>
  pedir<VistaPrevia>("/busquedas/vista-previa", { metodo: "POST", cuerpo: pedido });

export const ejecutar = (id: string) =>
  pedir<unknown>(`/busquedas/${encodeURIComponent(id)}/ejecutar`, { metodo: "POST" });

export type EstadoIntake = { frase: boolean; lookalike: boolean };
export type Sugerencia = {
  pais: string;
  ciiu: string | null;
  departamento: string | null;
  ciudad: string | null;
  ingresos_min: number | null;
  palabras_clave: string[];
  exclusiones: string[];
};

export const estadoIntake = () => pedir<EstadoIntake>("/intake/estado");

export const sugerirDesdeFrase = (frase: string) =>
  pedir<{ sugerencia: Sugerencia; costo_usd: string }>("/intake/frase", { metodo: "POST", cuerpo: { frase } });
