import i18n from "../i18n";

export const SIN_DATO = "—";

const formatear = (opciones: Intl.NumberFormatOptions, valor: number) =>
  new Intl.NumberFormat(i18n.language, opciones).format(valor);

/** USD en el idioma activo. La API manda decimales como string; null es "sin dato", nunca 0. */
export function moneda(valor: string | number | null): string {
  return valor === null ? SIN_DATO : formatear({ style: "currency", currency: "USD" }, Number(valor));
}

export function entero(valor: number | null): string {
  return valor === null ? SIN_DATO : formatear({}, valor);
}

/** Marca de enlace que sale de la app (las atribuciones de licencia abren en pestaña nueva). */
export const FLECHA_EXTERNA = "↗";

/** USD con hasta 6 decimales: el costo máximo de una búsqueda son fracciones de centavo y `moneda` lo mostraría como $0.00. */
export function monedaFina(valor: string | number | null): string {
  return valor === null
    ? SIN_DATO
    : formatear({ style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 }, Number(valor));
}

/** parte / todo como porcentaje; sin dato o todo 0 es "sin dato", nunca una división por cero. */
export function porcentaje(parte: number | null, todo: number | null): string {
  return parte === null || !todo ? SIN_DATO : formatear({ style: "percent", maximumFractionDigits: 1 }, parte / todo);
}
