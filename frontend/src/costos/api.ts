import { pedir } from "../api/cliente";
import type { PaginaCostos } from "./tipos";

/** Una página del libro de costos del tenant; con `busquedaId`, solo lo de esa búsqueda (totales incluidos). */
export const listarCostos = (pagina: number, busquedaId: string | null) =>
  pedir<PaginaCostos>(`/costos?pagina=${pagina}${busquedaId ? `&busqueda_id=${encodeURIComponent(busquedaId)}` : ""}`);
