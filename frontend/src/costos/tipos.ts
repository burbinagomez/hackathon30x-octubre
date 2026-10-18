/** Una operación del libro. Decimales como string. `lead` es solo si hay lead: la API nunca manda su id. */
export type FilaCosto = {
  ts: string;
  tipo: string;
  fuente: string | null;
  proveedor: string;
  cantidad: string;
  costo_usd: string;
  gratis: boolean;
  busqueda_id: string | null;
  lote_id: string | null;
  lead: boolean;
};

export type PaginaCostos = {
  items: FilaCosto[];
  total: number;
  pagina: number;
  tamano: number;
  total_usd: string;
  total_real_usd: string;
  por_tipo: { tipo: string; costo_usd: string }[];
  por_fuente: { fuente: string; costo_usd: string }[];
};
