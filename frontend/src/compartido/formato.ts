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

/** USD con hasta 6 decimales: el costo máximo de una búsqueda son fracciones de centavo y `moneda` lo mostraría como $0.00. */
export function monedaFina(valor: string | number | null): string {
  return valor === null
    ? SIN_DATO
    : formatear({ style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 }, Number(valor));
}
