export type Actividad = { codigo: string; nombre_es: string; nombre_en: string | null };

export type PedidoVistaPrevia = {
  pais: string;
  ciiu: string;
  departamento?: string;
  ingresos_min?: number;
  palabras_clave: string[];
  exclusiones: string[];
  canal_preferido: string;
  tope_gasto_usd: number;
  mensaje_base: string;
};

export type FuenteVistaPrevia = {
  fuente: string;
  conteo: number | null;
  motivo: string | null;
  ignorados: string[];
  truncado: boolean;
};

/** Los montos son decimales como string, tal como los serializa la API. `null` = la API todavía no lo calcula (o no lo
 *  aplica, como el tope): no se pinta y nunca se lee como 0. */
export type VistaPrevia = {
  busqueda_id: string;
  fuentes: FuenteVistaPrevia[];
  descartadas: { fuente: string; motivo: string }[];
  costo_vista_previa_usd: string | null;
  costo_estimado_usd: string | null;
  costo_maximo_usd: string | null;
  creditos_restantes_mes: number | null;
  requests_restantes_24h: number | null;
  dentro_del_tope: boolean | null;
};
