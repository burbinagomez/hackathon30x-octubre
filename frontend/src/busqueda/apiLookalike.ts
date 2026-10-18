import { pedir } from "../api/cliente";

/** Forma del body de vista previa que la Puerta A puede prellenar (spec 010, ajuste 1). Códigos, nunca nombres. */
export type SugerenciaIntake = {
  pais: string;
  ciiu: string | null;
  departamento: string | null; // código nativo de la división
  ciudad: string | null;
  ingresos_min: number | null;
  palabras_clave: string[];
  exclusiones: string[];
};

export type RespuestaLookalike = {
  sugerencia: SugerenciaIntake;
  explicacion: { ciiu: [string, number][]; departamento: [string, number][] };
  resueltos: number;
  no_resueltos: string[];
  costo_usd: string;
};

export const lookalike = (nombres: string[]) =>
  pedir<RespuestaLookalike>("/intake/lookalike", { metodo: "POST", cuerpo: { nombres } });
