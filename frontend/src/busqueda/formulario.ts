import type { Sugerencia } from "./api";
import type { PedidoVistaPrevia } from "./tipos";

export type Formulario = Record<
  "pais" | "ciiu" | "departamento" | "ciudad" | "ingresosMin" | "palabrasClave" | "exclusiones" | "canal" | "tope" | "mensaje",
  string
>;
export const INICIAL: Formulario = {
  pais: "CO", ciiu: "", departamento: "", ciudad: "", ingresosMin: "", palabrasClave: "",
  exclusiones: "", canal: "email", tope: "", mensaje: "",
};

/** La sugerencia de una puerta pisa solo los criterios del ICP; canal, tope y mensaje son del usuario. */
export function conSugerencia(f: Formulario, s: Sugerencia): Formulario {
  return {
    ...f,
    pais: s.pais,
    ciiu: s.ciiu ?? "",
    departamento: s.departamento ?? "",
    ciudad: s.departamento && s.ciudad ? s.ciudad : "",
    ingresosMin: s.ingresos_min === null ? "" : String(s.ingresos_min),
    palabrasClave: s.palabras_clave.join(", "),
    exclusiones: s.exclusiones.join(", "),
  };
}

const lista = (texto: string) => texto.split(",").map((p) => p.trim()).filter(Boolean);

export function aPedido(f: Formulario): PedidoVistaPrevia {
  return {
    pais: f.pais,
    ciiu: f.ciiu,
    // Códigos, no nombres. La ciudad solo viaja dentro de una división (el select de división lo garantiza).
    departamento: f.departamento || undefined,
    ciudad: f.departamento && f.ciudad.trim() ? f.ciudad.trim() : undefined,
    ingresos_min: f.ingresosMin ? Number(f.ingresosMin) : undefined,
    palabras_clave: lista(f.palabrasClave),
    exclusiones: lista(f.exclusiones),
    canal_preferido: f.canal,
    tope_gasto_usd: Number(f.tope),
    mensaje_base: f.mensaje,
  };
}
