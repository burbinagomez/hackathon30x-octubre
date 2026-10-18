/** Montos como decimales en string; null es "sin dato" (CPL sin divisor, por ejemplo). */
export type FilaTablero = {
  fuente: string;
  encontrados: number;
  unicos: number;
  icp: number;
  costo_lista: string;
  costo_real: string;
  desperdicio_lista: string;
  desperdicio_real: string;
  cpl_lista: string | null;
  cpl_real: string | null;
  cuenta_naturales: boolean;
  naturales_no_contactables: number | null;
};

export type Tablero = {
  fuentes: FilaTablero[];
  total: FilaTablero;
  costo_evals: string;
  cobertura: { pais: string; fuentes: string[] }[];
  revisiones_pendientes: number;
  atribuciones: { fuente: string; texto: string; url: string }[];
};
