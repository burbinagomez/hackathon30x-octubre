import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import i18n from "../i18n";
import { monto } from "../test/fixtures";
import { server } from "../test/servidor";
import Costos from "./Costos";

const BUSQUEDA = "11111111-1111-4111-8111-111111111111";
const fila = (n: number, extra = {}) => ({
  ts: `2026-10-18T12:0${n}:00+00:00`, tipo: "overpass_query", fuente: "osm_overpass", proveedor: "overpass", cantidad: "1",
  costo_usd: "0.5", gratis: false, busqueda_id: BUSQUEDA, lote_id: BUSQUEDA, lead: false, ...extra,
});
const respuesta = (extra = {}) => ({
  items: [fila(3, { tipo: "web_fetch", fuente: "sitio_web", proveedor: "web", lead: true, busqueda_id: null, lote_id: null }),
          fila(2, { tipo: "croma_consulta", fuente: "croma_supersociedades_co", gratis: true }), fila(1)],
  total: 3, pagina: 1, tamano: 50, total_usd: "1.5", total_real_usd: "1.0",
  por_tipo: [{ tipo: "overpass_query", costo_usd: "0.75" }, { tipo: "web_fetch", costo_usd: "0.75" }],
  por_fuente: [{ fuente: "osm_overpass", costo_usd: "0.75" }, { fuente: "sin_atribuir", costo_usd: "0.75" }],
  ...extra,
});

async function montar(cuerpo: unknown, idioma = "es", busqueda: string | null = null) {
  const pedidos: string[] = [];
  server.use(http.get("*/costos", ({ request }) => {
    const url = new URL(request.url);
    pedidos.push(url.search);
    return HttpResponse.json({ ...(cuerpo as object), pagina: Number(url.searchParams.get("pagina")) });
  }));
  await i18n.changeLanguage(idioma);
  render(<Costos busquedaId={busqueda} />);
  return pedidos;
}

test("pinta el total, los subtotales y las filas", async () => {
  await montar(respuesta());
  await waitFor(() => expect(screen.queryByRole("table", { name: "Operaciones" })).toBeInTheDocument());
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Libro de costos");
  expect(screen.getByTestId("total-usd")).toHaveTextContent(monto("es", "1.5"));
  const porTipo = within(screen.getByRole("region", { name: "Por tipo" }));
  expect(porTipo.getByText("Consulta de web")).toBeInTheDocument();
  expect(porTipo.getAllByText(monto("es", "0.75"))).toHaveLength(2);
  const porFuente = within(screen.getByRole("region", { name: "Por fuente" }));
  expect(porFuente.getByText("OpenStreetMap")).toBeInTheDocument();
  expect(porFuente.getByText("Sin atribuir")).toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(4); // cabecera + 3
});

test("la tabla vive en un contenedor con scroll horizontal", async () => {
  await montar(respuesta());
  const tabla = await screen.findByRole("table", { name: "Operaciones" });
  expect(tabla.closest(".tabla-scroll")).not.toBeNull();
});

test("la fila de un lead dice solo si, sin id", async () => {
  await montar(respuesta());
  const filas = await screen.findAllByRole("row");
  expect(within(filas[1]).getAllByRole("cell").map((c) => c.textContent)).toContain("Sí");
  expect(within(filas[3]).getAllByRole("cell").map((c) => c.textContent)).not.toContain("Sí");
});

test("sin busqueda no filtra; con busqueda manda busqueda_id y lo avisa", async () => {
  const sin = await montar(respuesta());
  await screen.findByRole("table");
  expect(sin).toEqual(["?pagina=1"]);
});

test("con filtro por busqueda lo manda a la API y ofrece quitarlo", async () => {
  const pedidos = await montar(respuesta(), "es", BUSQUEDA);
  await screen.findByRole("table");
  expect(pedidos).toEqual([`?pagina=1&busqueda_id=${BUSQUEDA}`]);
  expect(screen.getByText(/Filtrado por búsqueda/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Ver todo el libro" })).toHaveAttribute("href", "/costos");
});

test("pagina de a 50: siguiente y anterior piden la pagina", async () => {
  const pedidos = await montar(respuesta({ total: 120 }));
  await screen.findByRole("table");
  expect(screen.getByText("Página 1 de 3")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
  await waitFor(() => expect(pedidos).toContain("?pagina=2"));
  await waitFor(() => expect(screen.queryByText("Página 2 de 3")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Anterior" }));
  await waitFor(() => expect(pedidos.filter((p) => p === "?pagina=1")).toHaveLength(2));
});

test("en ingles", async () => {
  await montar(respuesta(), "en");
  await screen.findByRole("table", { name: "Operations" });
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Cost ledger");
  expect(screen.getByRole("region", { name: "By type" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "By source" })).toBeInTheDocument();
  expect(screen.getByText("Page 1 of 1")).toBeInTheDocument();
});

test("libro vacio lo dice", async () => {
  await montar(respuesta({ items: [], total: 0, total_usd: "0", total_real_usd: "0", por_tipo: [], por_fuente: [] }));
  await waitFor(() => expect(screen.queryByText("Todavía no hay costos registrados.")).toBeInTheDocument());
});

test("si la API falla muestra el error", async () => {
  server.use(http.get("*/costos", () => new HttpResponse(null, { status: 500 })));
  await i18n.changeLanguage("es");
  render(<Costos busquedaId={null} />);
  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent("No se pudo cargar el libro de costos."));
});

test("los montos de fracciones de centavo no se redondean a 0,00", async () => {
  // QA 2026-10-18: el libro real mostraba "Total: 0,00 US$" con operaciones de 0,00003 US$.
  await montar(respuesta({ total_usd: "0.000032", total_real_usd: "0.000032",
    por_tipo: [{ tipo: "socrata_descarga", costo_usd: "0.00003" }], por_fuente: [{ fuente: "datos_gov_co_rues", costo_usd: "0.00003" }] }));
  await waitFor(() => expect(screen.getByTestId("total-usd")).toBeInTheDocument());
  expect(screen.getByTestId("total-usd").textContent).not.toMatch(/^0,00\s?US\$$/);
  expect(screen.getByTestId("total-usd")).toHaveTextContent("0,000032");
  expect(within(screen.getByRole("region", { name: "Por tipo" })).getByText(/0,00003/)).toBeInTheDocument();
});

test("la cantidad lleva su unidad: segundos de cómputo o créditos", async () => {
  await montar(respuesta({ items: [fila(1, { tipo: "socrata_descarga", cantidad: "4.298" }),
                                   fila(2, { tipo: "croma_consulta", cantidad: "1" })] }));
  const tabla = within(await screen.findByRole("table", { name: "Operaciones" }));
  expect(tabla.getByText("4,298 s")).toBeInTheDocument();
  expect(tabla.getByText("1 crédito")).toBeInTheDocument();
});
