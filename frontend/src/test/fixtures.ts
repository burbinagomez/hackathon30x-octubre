import { http, HttpResponse } from "msw";
import { expect } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "./servidor";
import { estado } from "./supabaseFalso";

/** Campo por etiqueta; si falta, falla con un assert y no con una excepción de Testing Library. */
export function campo(etiqueta: string): HTMLElement {
  const el = screen.queryByLabelText(etiqueta);
  expect(el, `falta el campo "${etiqueta}"`).toBeInTheDocument();
  return el as HTMLElement;
}

/** Botón por nombre, con el mismo criterio. */
export function boton(nombre: string): HTMLElement {
  const el = screen.queryByRole("button", { name: nombre });
  expect(el, `falta el botón "${nombre}"`).toBeInTheDocument();
  return el as HTMLElement;
}

/** Sesión de Supabase abierta (token de prueba) y los idiomas que el front guarda tras GET /usuarios/me. */
export function iniciarSesion(
  idiomas: { usuario?: "es" | "en" | null; tenant?: "es" | "en" } = {},
) {
  estado.sesion = { access_token: "jwt-de-prueba" };
  const usuario = idiomas.usuario ?? null;
  if (usuario) sessionStorage.setItem("idioma_usuario", usuario);
  sessionStorage.setItem("idioma_tenant", idiomas.tenant ?? "es");
}

/** Captura los body de PATCH /usuarios/me. */
export function espiarFijarIdioma() {
  const cuerpos: unknown[] = [];
  server.use(
    http.patch("*/usuarios/me", async ({ request }) => {
      cuerpos.push(await request.json());
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return cuerpos;
}

export const actividades = [
  { codigo: "1081", nombre_es: "Elaboración de productos de panadería", nombre_en: "Manufacture of bakery products" },
  { codigo: "4631", nombre_es: "Comercio al por mayor de alimentos", nombre_en: null },
];

/** GET /geografia: solo un pedazo de los 33; el código es DIVIPOLA y es lo que viaja en el pedido. */
export const geografia = {
  CO: [
    { codigo: "05", nombre_es: "Antioquia", nombre_en: "Antioquia" },
    { codigo: "11", nombre_es: "Bogotá, D.C.", nombre_en: "Bogotá, D.C." },
    { codigo: "73", nombre_es: "Tolima", nombre_en: "Tolima" },
    { codigo: "88", nombre_es: "San Andrés y Providencia", nombre_en: "San Andrés and Providencia" },
  ],
};

export function respuestaVistaPrevia(cambios: Record<string, unknown> = {}) {
  return {
    busqueda_id: "b-1",
    fuentes: [
      { fuente: "croma_supersociedades_co", conteo: 100, motivo: null, ignorados: [], truncado: true },
      { fuente: "osm_overpass", conteo: 7, motivo: null, ignorados: ["ingresos_min"], truncado: false },
    ],
    descartadas: [{ fuente: "datos_gov_co_rues", motivo: "sin_mapeo_actividad" }],
    costo_vista_previa_usd: "0.4000",
    costo_estimado_usd: "0.9000",
    costo_maximo_usd: "1.4000",
    creditos_restantes_mes: 288,
    requests_restantes_24h: 63,
    dentro_del_tope: true,
    ...cambios,
  };
}

/** Lo que devuelve la API del [MIN]: sin `contar` ni costos, y el tope todavía no se aplica (null, nunca 0). */
export function respuestaVistaPreviaMinima(cambios: Record<string, unknown> = {}) {
  return respuestaVistaPrevia({
    fuentes: [
      { fuente: "osm_overpass", conteo: null, motivo: "sin_conteo", ignorados: ["palabras_clave", "exclusiones"], truncado: false },
      { fuente: "datos_gov_co_rues", conteo: null, motivo: "sin_conteo", ignorados: ["ciudad"], truncado: false },
    ],
    descartadas: [],
    costo_vista_previa_usd: null,
    costo_estimado_usd: null,
    costo_maximo_usd: null,
    creditos_restantes_mes: null,
    requests_restantes_24h: null,
    dentro_del_tope: null,
    ...cambios,
  });
}

/** El tablero del [MIN]: solo encontrados y únicos; todo lo demás, null. */
export function respuestaTableroMinima(cambios: Record<string, unknown> = {}) {
  const fila = {
    icp: null, costo_lista: null, costo_real: null, desperdicio_lista: null, desperdicio_real: null,
    cpl_lista: null, cpl_real: null, cuenta_naturales: false, naturales_no_contactables: null,
  };
  return {
    fuentes: [{ ...fila, fuente: "osm_overpass", encontrados: 3, unicos: 2 }],
    total: { ...fila, fuente: "TOTAL", encontrados: 3, unicos: 2 },
    costo_evals: null,
    cobertura: null,
    revisiones_pendientes: null,
    atribuciones: [] as { fuente: string; texto: string; url: string }[],
    ...cambios,
  };
}

const filaTablero = {
  encontrados: 4,
  unicos: 4,
  icp: 4,
  costo_lista: "1.3500",
  costo_real: "0.9500",
  desperdicio_lista: "0.5000",
  desperdicio_real: "0.5000",
  cpl_lista: "0.3375",
  cpl_real: "0.2375",
  cuenta_naturales: false,
  naturales_no_contactables: null,
};

export function respuestaTablero(cambios: Record<string, unknown> = {}) {
  return {
    fuentes: [
      { ...filaTablero, fuente: "croma_supersociedades_co" },
      { ...filaTablero, fuente: "sin_atribuir", encontrados: 0, unicos: 0, icp: 0, cpl_lista: null, cpl_real: null },
    ],
    total: { ...filaTablero, fuente: "TOTAL" },
    costo_evals: "1.0000",
    cobertura: [{ pais: "CO", fuentes: ["croma_supersociedades_co", "osm_overpass"] }],
    revisiones_pendientes: 3,
    atribuciones: [] as { fuente: string; texto: string; url: string }[],
    ...cambios,
  };
}

export const atribucionOsm = {
  fuente: "osm_overpass",
  texto: "© OpenStreetMap contributors",
  url: "https://www.openstreetmap.org/copyright",
};
export const atribucionDatosGov = {
  fuente: "datos_gov_co_rues",
  texto: "Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)",
  url: "https://creativecommons.org/licenses/by-sa/4.0/",
};

/** Monto como lo formatea la UI (USD, idioma activo); los espacios duros pasan a normales, como en el DOM. */
export function monto(idioma: "es" | "en", valor: number | string): string {
  return new Intl.NumberFormat(idioma, { style: "currency", currency: "USD" })
    .format(Number(valor))
    .replace(/\s/g, " ");
}

export function numero(idioma: "es" | "en", valor: number): string {
  return new Intl.NumberFormat(idioma).format(valor).replace(/\s/g, " ");
}
