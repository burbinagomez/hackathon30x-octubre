/** Montos como decimales en string; null es "sin dato" (CPL sin divisor, por ejemplo). */
export type FilaTablero = {
  fuente: string;
  encontrados: number;
  unicos: number;
  icp: number | null;
  costo_lista: string | null;
  costo_real: string | null;
  desperdicio_lista: string | null;
  desperdicio_real: string | null;
  cpl_lista: string | null;
  cpl_real: string | null;
  cuenta_naturales: boolean;
  naturales_no_contactables: number | null;
  /** Embudo: conteos de leads únicos. null = no aplica (sin_atribuir); nunca un 0 inventado. */
  enriquecidos: number | null;
  contactables: number | null;
  con_telefono: number | null;
  calificados: number | null;
};

export type Tablero = {
  fuentes: FilaTablero[];
  total: FilaTablero;
  costo_evals: string | null;
  cobertura: { pais: string; fuentes: string[] }[] | null;
  revisiones_pendientes: number | null;
  atribuciones: { fuente: string; texto: string; url: string }[];
};

/** Una fila de GET /calificaciones/cpql. Sin calificados el CPQL es null ("sin dato"), nunca una división por cero. */
export type FilaCpql = {
  fuente: string;
  costo_lista: string | null;
  costo_real: string | null;
  calificados: number;
  cpql_lista: string | null;
  cpql_real: string | null;
};

export type Cpql = { fuentes: FilaCpql[]; total: FilaCpql | null };

/** Resumen de POST /calificaciones/importar. Los contactos nunca vuelven en la respuesta. */
export type ResumenImportacion = {
  importadas: number;
  duplicadas: number;
  conflictos: number;
  no_cumple: number;
  ref_desconocida: number;
  rechazadas: { fila: number; motivo: string }[];
};
