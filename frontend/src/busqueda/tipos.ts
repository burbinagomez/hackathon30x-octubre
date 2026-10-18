export type Actividad = { codigo: string; nombre_es: string; nombre_en: string | null };

export type Municipio = { codigo_nativo: string; nombre: string };
/** División de primer nivel de un país. `codigo_nativo` (DIVIPOLA en CO) es lo que viaja en el pedido; `iso_3166_2` es el común. */
export type Division = {
  iso_3166_2: string;
  codigo_nativo: string;
  nombre_es: string;
  nombre_en: string;
  municipios: Municipio[];
};
/** GET /geografia: los países que tienen archivo. GET /geografia?pais=CO: sus divisiones con municipios. */
export type PaisesConGeografia = { paises: string[] };
export type GeografiaDePais = { pais: string; divisiones: Division[] };

export type PedidoVistaPrevia = {
  pais: string;
  ciiu: string;
  departamento?: string; // código nativo de la división ("73" en CO), nunca el nombre
  ciudad?: string; // nombre del municipio, dentro de esa división
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

/** Estados por fuente de POST /busquedas/{id}/ejecutar (spec 015). Códigos; el texto lo pone el front. */
export type EstadoFuente =
  | "con_resultados"
  | "sin_resultados"
  | "no_disponible"
  | "no_soporta_criterio"
  | "limite_agotado"
  | "omitida_por_tope";
export type ResultadoFuente = { estado: string; encontrados: number }; // `string`: un estado nuevo del back no rompe el front
export type PorFuente = Record<string, ResultadoFuente>;
export type ResultadoEjecucion = { busqueda_id: string; estado: string; por_fuente: PorFuente };
