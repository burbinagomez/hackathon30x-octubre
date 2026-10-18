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

export type Turno = { rol: "usuario" | "asistente"; texto: string };
export type RespuestaFrase = {
  sugerencia: Sugerencia;
  pregunta: string | null;
  explicacion: string | null;
  /** La IA propuso un CIIU que no está en el catálogo y quedó en null. */
  ciiu_descartado?: boolean;
  costo_usd: string;
};

/** Un turno de la conversación: la frase nueva y los turnos previos (el back acepta hasta 12). */
export const sugerirDesdeFrase = (frase: string, historial: Turno[] = []) =>
  pedir<RespuestaFrase>("/intake/frase", { metodo: "POST", cuerpo: { frase, historial } });
