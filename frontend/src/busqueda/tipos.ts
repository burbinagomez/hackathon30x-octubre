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

/** Los montos son decimales como string, tal como los serializa la API. */
export type VistaPrevia = {
  busqueda_id: string;
  fuentes: FuenteVistaPrevia[];
  descartadas: { fuente: string; motivo: string }[];
  costo_vista_previa_usd: string;
  costo_estimado_usd: string;
  costo_maximo_usd: string;
  creditos_restantes_mes: number;
  requests_restantes_24h: number;
  dentro_del_tope: boolean;
};
