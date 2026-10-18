import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import i18n from "../i18n";
import en from "../i18n/en.json";
import es from "../i18n/es.json";
import {
  atribucionDatosGov,
  atribucionOsm,
  monto,
  numero,
  respuestaTablero,
  respuestaTableroMinima,
} from "../test/fixtures";
import { server } from "../test/servidor";
import Tablero from "./Tablero";

type Idioma = "es" | "en";
const textos = { es, en };

const CPQL_VACIO = { fuentes: [], total: null };

/** `cpql`: la respuesta de /calificaciones/cpql, o un status para simular que falla. Por defecto, vacía. */
async function montar(respuesta: Record<string, unknown>, idioma: Idioma = "es", cpql: Record<string, unknown> | number = CPQL_VACIO) {
  server.use(
    http.get("*/tablero/fuentes", () => HttpResponse.json(respuesta)),
    http.get("*/calificaciones/cpql", () =>
      typeof cpql === "number" ? new HttpResponse(null, { status: cpql }) : HttpResponse.json(cpql)),
  );
  await i18n.changeLanguage(idioma);
  render(<Tablero />);
  await waitFor(() => expect(screen.queryByRole("table")).toBeInTheDocument());
}

/** El texto de la celda de una fila (por nombre de fuente) y columna (por encabezado). */
function celda(fila: string, columna: string): string {
  const encabezados = screen.queryAllByRole("columnheader").map((h) => h.textContent);
  const columnaIdx = encabezados.indexOf(columna);
  expect(columnaIdx, `no hay columna "${columna}" en ${encabezados.join("|")}`).toBeGreaterThanOrEqual(0);
  const fila_ = screen.queryAllByRole("row").find((r) => within(r).queryAllByRole("cell")[0]?.textContent === fila);
  expect(fila_, `no hay fila "${fila}"`).toBeDefined();
  // textContent trae los espacios duros de Intl; los helpers de monto los normalizan igual.
  return (within(fila_!).queryAllByRole("cell")[columnaIdx]?.textContent ?? "").replace(/\s/g, " ");
}

test("cpl_null_se_muestra_sin_dato", async () => {
  await montar(respuestaTablero());
  for (const columna of ["CPL (lista)", "CPL (real)"]) {
    expect(celda("Sin atribuir", columna)).toBe("—");
  }
  expect(screen.queryByRole("table")).not.toHaveTextContent(/∞|Infinity|NaN/);
});

test("muestra_costo_lista_y_real", async () => {
  await montar(respuestaTablero());
  expect(celda("Supersociedades (Croma)", "Costo (lista)")).toBe(monto("es", "1.35"));
  expect(celda("Supersociedades (Croma)", "Costo (real)")).toBe(monto("es", "0.95"));
  expect(celda("Supersociedades (Croma)", "CPL (lista)")).toBe(monto("es", "0.3375"));
  expect(celda("Supersociedades (Croma)", "CPL (real)")).toBe(monto("es", "0.2375"));
  expect(celda("Total", "Costo (lista)")).toBe(monto("es", "1.35"));
});

test("costo_de_evals_va_aparte", async () => {
  await montar(respuestaTablero({ costo_evals: "1.0000" }));
  expect(screen.queryByText(`Costo de evals (aparte): ${monto("es", "1")}`)).toBeInTheDocument();
  expect(within(screen.getByRole("table")).queryByText(/evals/i)).not.toBeInTheDocument();
});

test.each([
  ["ambas", [atribucionOsm, atribucionDatosGov]],
  ["solo_osm", [atribucionOsm]],
  ["ninguna", []],
])("muestra_atribucion_de_las_fuentes_presentes[%s]", async (_caso, atribuciones) => {
  await montar(respuestaTablero({ atribuciones }));
  const todas = [atribucionOsm, atribucionDatosGov];
  for (const a of todas) {
    const enlace = screen.queryByRole("link", { name: a.texto });
    if (atribuciones.includes(a)) {
      expect(enlace).toHaveAttribute("href", a.url);
    } else {
      expect(enlace).not.toBeInTheDocument();
    }
  }
  if (atribuciones.length === 0) {
    expect(screen.queryByLabelText("Atribución de datos")).not.toBeInTheDocument();
  }
});

test("muestra_cobertura_por_pais", async () => {
  await montar(respuestaTablero());
  const pais = screen.queryAllByRole("listitem").find((li) => li.textContent?.startsWith("CO"));
  expect(pais).toHaveTextContent("Supersociedades (Croma)");
  expect(pais).toHaveTextContent("OpenStreetMap");
});

test("muestra_revisiones_pendientes", async () => {
  await montar(respuestaTablero({ revisiones_pendientes: 3 }));
  expect(screen.queryByText("Revisiones pendientes: 3")).toBeInTheDocument();
});

const filaNaturales = (fuente: string, cuenta: boolean, naturales: number | null) => ({
  ...respuestaTablero().fuentes[0],
  fuente,
  cuenta_naturales: cuenta,
  naturales_no_contactables: naturales,
});

// Los tres estados de la 011: número contado, conteo fallido (null) y fuente que no cuenta naturales.
test.each<Idioma>(["es", "en"])("muestra_naturales_encontradas_no_contactables[%s]", async (idioma) => {
  const t = textos[idioma].tablero;
  await montar(
    respuestaTablero({
      fuentes: [
        filaNaturales("datos_gov_co_rues", true, 26304),
        filaNaturales("osm_overpass", true, null),
        filaNaturales("croma_supersociedades_co", false, null),
      ],
    }),
    idioma,
  );
  const f = textos[idioma].fuentes;
  expect(celda(f.datos_gov_co_rues, t.naturales)).toBe(numero(idioma, 26304));
  expect(celda(f.osm_overpass, t.naturales)).toBe("—");
  expect(celda(f.croma_supersociedades_co, t.naturales)).toBe(t.no_aplica);
});

test("el_minimo_pinta_encontrados_y_unicos_y_no_las_columnas_de_costo_ni_las_secciones_sin_dato", async () => {
  await montar(respuestaTableroMinima({ atribuciones: [atribucionOsm] }));

  const encabezados = screen.queryAllByRole("columnheader").map((h) => h.textContent);
  expect(encabezados).toEqual(["Fuente", "Encontrados", "Únicos"]);
  expect(celda("OpenStreetMap", "Encontrados")).toBe("3");
  expect(celda("Total", "Únicos")).toBe("2");
  expect(screen.queryByText(/evals/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Revisiones pendientes/)).not.toBeInTheDocument();
  expect(screen.queryByText(es.tablero.cobertura)).not.toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/NaN|—|No aplica/);
  expect(screen.queryByRole("link", { name: atribucionOsm.texto })).toBeInTheDocument();  // la atribución sí
});

const sinDesperdicio = { desperdicio_lista: null, desperdicio_real: null };

test("con_costos_y_sin_desperdicio_muestra_costo_y_cpl_y_no_columnas_vacias", async () => {
  const base = respuestaTablero();
  await montar({
    ...base,
    fuentes: base.fuentes.map((f) => ({ ...f, ...sinDesperdicio })),
    total: { ...base.total, ...sinDesperdicio },
  });

  const encabezados = screen.queryAllByRole("columnheader").map((h) => h.textContent);
  expect(encabezados).toEqual(["Fuente", "Encontrados", "Únicos", "Costo (lista)", "Costo (real)", "CPL (lista)", "CPL (real)"]);
  expect(celda("Total", "CPL (lista)")).toBe(monto("es", "0.3375"));
});

test("fuente_sin_costo_registrado_muestra_sin_dato_y_nunca_cero", async () => {
  const base = respuestaTablero();
  const sinCosto = { ...base.fuentes[0], fuente: "osm_overpass", costo_lista: null, costo_real: null, cpl_lista: null, cpl_real: null };
  await montar({ ...base, fuentes: [base.fuentes[0], sinCosto] });

  for (const columna of ["Costo (lista)", "Costo (real)", "CPL (lista)", "CPL (real)"]) {
    expect(celda("OpenStreetMap", columna)).toBe("—");
  }
  expect(celda("OpenStreetMap", "CPL (lista)")).not.toMatch(/0[.,]00/);
});

test("costo_y_cpl_en_ingles_con_moneda_del_idioma", async () => {
  await montar(respuestaTablero(), "en");
  const t = en.tablero;
  expect(celda(en.fuentes.croma_supersociedades_co, t.costo_lista)).toBe(monto("en", "1.35"));
  expect(celda(en.fuentes.croma_supersociedades_co, t.cpl_real)).toBe(monto("en", "0.2375"));
  expect(celda(en.fuentes.sin_atribuir, t.cpl_lista)).toBe("—");
});

test("enlaza_a_ver_busquedas", async () => {
  await montar(respuestaTablero());
  expect(screen.getByRole("link", { name: "Ver búsquedas" })).toHaveAttribute("href", "/busquedas");
});

test("cada_fila_de_fuente_lleva_a_sus_leads_y_el_total_a_todos", async () => {
  await montar(respuestaTablero());
  expect(screen.getByRole("link", { name: "Supersociedades (Croma)" })).toHaveAttribute("href", "/leads?fuente=croma_supersociedades_co");
  expect(screen.getByRole("link", { name: "Total" })).toHaveAttribute("href", "/leads");
  // sin_atribuir son costos sin lead: no hay lista a la que llevar.
  expect(screen.queryByRole("link", { name: "Sin atribuir" })).not.toBeInTheDocument();
});

test("el_clic_en_una_fila_navega_sin_recargar", async () => {
  await montar(respuestaTablero());
  const antes = window.location.href;
  fireEvent.click(screen.getByRole("link", { name: "Supersociedades (Croma)" }));
  expect(window.location.pathname + window.location.search).toBe("/leads?fuente=croma_supersociedades_co");
  expect(antes).not.toBe(window.location.href);
});

test("la_atribucion_es_externa_y_dice_licencia", async () => {
  await montar(respuestaTablero({ atribuciones: [atribucionOsm] }));
  const pie = screen.getByLabelText("Atribución de datos");
  expect(pie).toHaveTextContent("Licencia");
  const enlace = within(pie).getByRole("link", { name: atribucionOsm.texto });
  expect(enlace).toHaveAttribute("target", "_blank");
  expect(enlace).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
  expect(enlace).toHaveTextContent("↗");
});

const filaCpql = (fuente: string, calificados: number, costo: string | null, cpql: string | null) => ({
  fuente, costo_lista: costo, costo_real: costo, calificados, cpql_lista: cpql, cpql_real: cpql,
});

/** El tablero de `respuestaTablero` (croma con 4 únicos) más una fuente sin calificados y el CPQL de las dos. */
function conCpql() {
  const base = respuestaTablero();
  const osm = { ...base.fuentes[0], fuente: "osm_overpass" };
  return {
    tablero: { ...base, fuentes: [base.fuentes[1], base.fuentes[0], osm] },  // sin_atribuir primero: se pinta al final
    cpql: {
      fuentes: [
        filaCpql("croma_supersociedades_co", 2, "1.35", "0.675"),
        filaCpql("osm_overpass", 0, "1.35", null),
        filaCpql("sin_atribuir", 0, "0.999", null),
      ],
      total: filaCpql("TOTAL", 2, "3.699", "1.8495"),
    },
  };
}

const fina = (idioma: Idioma, valor: string) =>
  new Intl.NumberFormat(idioma, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 })
    .format(Number(valor)).replace(/\s/g, " ");
const pct = (idioma: Idioma, valor: number) =>
  new Intl.NumberFormat(idioma, { style: "percent", maximumFractionDigits: 1 }).format(valor).replace(/\s/g, " ");

test.each(["es", "en"] as const)("muestra_calificados_porcentaje_y_cpql_por_fuente[%s]", async (idioma) => {
  const { tablero, cpql } = conCpql();
  await montar(tablero, idioma, cpql);
  const t = textos[idioma].tablero;
  const croma = textos[idioma].fuentes.croma_supersociedades_co;

  expect(celda(croma, t.calificados)).toBe(numero(idioma, 2));
  expect(celda(croma, t.pct_calificados)).toBe(pct(idioma, 0.5));  // 2 calificados / 4 únicos
  expect(celda(croma, t.cpql)).toBe(fina(idioma, "0.675"));
  expect(celda(t.total, t.calificados)).toBe(numero(idioma, 2));
  expect(celda(t.total, t.cpql)).toBe(fina(idioma, "1.8495"));
});

test("fuente_sin_calificados_muestra_cpql_sin_dato_y_nunca_divide_por_cero", async () => {
  const { tablero, cpql } = conCpql();
  await montar(tablero, "es", cpql);

  expect(celda("OpenStreetMap", es.tablero.calificados)).toBe("0");
  expect(celda("OpenStreetMap", es.tablero.cpql)).toBe("—");
  expect(screen.getByRole("table")).not.toHaveTextContent(/∞|Infinity|NaN/);
});

test("sin_atribuir_va_al_final_solo_con_costo_y_con_otro_estilo", async () => {
  const { tablero, cpql } = conCpql();
  await montar(tablero, "es", cpql);

  const filas = screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);
  expect(filas.slice(-2)).toEqual(["Sin atribuir", "Total"]);
  for (const columna of [es.tablero.calificados, es.tablero.pct_calificados, es.tablero.cpql]) {
    expect(celda("Sin atribuir", columna)).toBe("");
  }
  expect(celda("Sin atribuir", "Costo (lista)")).toBe(monto("es", "1.35"));
  const fila = screen.getAllByRole("row").find((r) => within(r).queryAllByRole("cell")[0]?.textContent === "Sin atribuir");
  expect(fila).toHaveClass("sin-atribuir");
});

test.each([["falla", 500], ["vacio", CPQL_VACIO]] as const)("cpql_%s_el_tablero_se_ve_como_antes", async (_caso, cpql) => {
  await montar(respuestaTablero(), "es", cpql);

  const encabezados = screen.queryAllByRole("columnheader").map((h) => h.textContent);
  expect(encabezados).not.toContain(es.tablero.cpql);
  expect(encabezados).not.toContain(es.tablero.calificados);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(celda("Supersociedades (Croma)", "Costo (lista)")).toBe(monto("es", "1.35"));
});

// --- Embudo por fuente: encontrados -> únicos -> enriquecidos -> contactables -> con teléfono -> calificados ---

/** Los pasos del grupo del embudo de una fuente como [etiqueta, valor], con los espacios normalizados. */
function pasosEmbudo(nombre: string): string[][] {
  const grupo = within(screen.getByRole("region", { name: /embudo|funnel/i })).getByRole("group", { name: nombre });
  return within(grupo).getAllByRole("listitem").map((li) =>
    [...li.querySelectorAll("[data-paso]")].map((e) => (e.textContent ?? "").replace(/\s/g, " ")));
}

test.each<[Idioma, string[]]>([
  ["es", ["75 %", "50 %", "50 %", "25 %"]],
  ["en", ["75%", "50%", "50%", "25%"]],
])("embudo_muestra_numero_y_porcentaje_de_unicos_en_orden[%s]", async (idioma, pct) => {
  const t = textos[idioma].tablero;
  const pct100 = idioma === "es" ? "100 %" : "100%";
  await montar(respuestaTablero(), idioma);
  const nombre = textos[idioma].fuentes.croma_supersociedades_co;
  expect(pasosEmbudo(nombre)).toEqual([
    [t.encontrados, "4", pct100],
    [t.unicos, "4", pct100],
    [t.embudo_enriquecidos, "3", pct[0]],
    [t.embudo_contactables, "2", pct[1]],
    [t.embudo_con_telefono, "2", pct[2]],
    [t.embudo_calificados, "1", pct[3]],
  ]);
  expect(screen.getByRole("region", { name: t.embudo })).toBeInTheDocument();
});

test("embudo_incluye_el_total_y_deja_fuera_sin_atribuir", async () => {
  await montar(respuestaTablero());
  const region = screen.getByRole("region", { name: "Embudo por fuente" });
  expect(within(region).getByRole("group", { name: "Total" })).toBeInTheDocument();
  expect(within(region).queryByRole("group", { name: "Sin atribuir" })).not.toBeInTheDocument();
});

test("embudo_la_barra_es_proporcional_a_unicos_y_usa_solo_tokens", async () => {
  await montar(respuestaTablero());
  const grupo = within(screen.getByRole("region", { name: "Embudo por fuente" })).getByRole("group", { name: "Supersociedades (Croma)" });
  const anchos = [...grupo.querySelectorAll<HTMLElement>(".embudo-barra")].map((b) => b.style.width);
  expect(anchos).toEqual(["100%", "100%", "75%", "50%", "50%", "25%"]);
  expect(grupo.querySelector("[style*='#'], [style*='rgb']")).toBeNull();
});

test("embudo_encontrados_mayor_que_unicos_no_desborda_la_barra", async () => {
  await montar(respuestaTablero({ fuentes: [{ ...respuestaTablero().fuentes[0], fuente: "osm_overpass", encontrados: 8, unicos: 7 }] }));
  const grupo = within(screen.getByRole("region", { name: "Embudo por fuente" })).getByRole("group", { name: "OpenStreetMap" });
  expect(grupo.querySelector<HTMLElement>(".embudo-barra")!.style.width).toBe("100%");
  expect(pasosEmbudo("OpenStreetMap")[0]).toEqual(["Encontrados", "8", "114,3 %"]);
});

test("embudo_sin_unicos_no_divide_por_cero_ni_pinta_barras", async () => {
  const vacia = { ...respuestaTablero().fuentes[0], encontrados: 0, unicos: 0, enriquecidos: 0, contactables: 0, con_telefono: 0, calificados: 0 };
  await montar(respuestaTablero({ fuentes: [vacia], total: { ...vacia, fuente: "TOTAL" } }));
  const region = screen.getByRole("region", { name: "Embudo por fuente" });
  expect(region).not.toHaveTextContent(/NaN|Infinity|∞/);
  expect(pasosEmbudo("Supersociedades (Croma)").map((p) => p[2])).toEqual(Array(6).fill("—"));
  expect([...region.querySelectorAll<HTMLElement>(".embudo-barra")].every((b) => b.style.width === "0%")).toBe(true);
});

test("embudo_sin_fuentes_ni_campos_no_rompe_la_pantalla", async () => {
  // Un backend viejo (sin los campos nuevos) o sin leads: la tabla se ve y el embudo no inventa nada.
  await montar(respuestaTableroMinima({ fuentes: [], total: { ...respuestaTableroMinima().total, encontrados: 0, unicos: 0 } }));
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Embudo por fuente" })).not.toBeInTheDocument();
});

test("embudo_con_campos_ausentes_muestra_sin_dato_y_nunca_cero", async () => {
  await montar(respuestaTableroMinima());
  const pasos = pasosEmbudo("OpenStreetMap");
  expect(pasos.slice(2).map((p) => p[1])).toEqual(["—", "—", "—", "—"]);
});

test("embudo_cada_paso_tiene_texto_visible_ademas_de_la_barra", async () => {
  await montar(respuestaTablero());
  const grupo = within(screen.getByRole("region", { name: "Embudo por fuente" })).getByRole("group", { name: "Supersociedades (Croma)" });
  for (const li of within(grupo).getAllByRole("listitem")) {
    expect(li.textContent).toMatch(/\d/);
    expect(li.querySelector(".embudo-pista")).toHaveAttribute("aria-hidden", "true");
  }
});
