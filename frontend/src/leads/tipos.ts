/** Contrato de GET /busquedas y GET /busquedas/{id}/leads. `tiene_*` null = sin dato; telefono/email/web solo de una jurídica. */
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
  // Solo de una jurídica: el canal que la empresa publica. Natural o sin dato: null.
  telefono?: string | null;
  email?: string | null;
  web?: string | null;
  // Clasificación contra el ICP: solo de una jurídica; null = natural o sin clasificar.
  encaje?: "encaja" | "no_encaja" | "ninguna" | null;
};

export type PaginaLeads = {
  items: LeadListado[];
  total: number;
  pagina: number;
  tamano: number;
  atribuciones: { fuente: string; texto: string; url: string }[];
};
