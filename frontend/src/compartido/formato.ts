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
