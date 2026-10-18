import { render, screen, waitFor, within } from "@testing-library/react";
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
} from "../test/fixtures";
import { server } from "../test/servidor";
import Tablero from "./Tablero";

type Idioma = "es" | "en";
const textos = { es, en };

async function montar(respuesta: ReturnType<typeof respuestaTablero>, idioma: Idioma = "es") {
  server.use(http.get("*/tablero/fuentes", () => HttpResponse.json(respuesta)));
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
