/** Contrato de GET /busquedas y GET /busquedas/{id}/leads. `tiene_telefono`/`tiene_email` null = sin dato; nunca el valor. */
export type Busqueda = {
  id: string;
  creada_en: string;
  estado: string;
  pais: string;
  departamento: string | null;
  ciudad: string | null;
  total_leads: number;
};

export type LeadListado = {
  id: string;
  nombre: string | null;
  tipo_titular: "juridica" | "natural" | "desconocido";
  fuentes: string[];
  licencias: string[];
  ciudad: string | null;
  tiene_web: boolean;
  tiene_telefono: boolean | null;
  tiene_email: boolean | null;
};

export type PaginaLeads = {
  items: LeadListado[];
  total: number;
  pagina: number;
  tamano: number;
  atribuciones: { fuente: string; texto: string; url: string }[];
};
