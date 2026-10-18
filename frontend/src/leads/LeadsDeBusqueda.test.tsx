import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import i18n from "../i18n";
import en from "../i18n/en.json";
import es from "../i18n/es.json";
import { server } from "../test/servidor";
import LeadsDeBusqueda from "./LeadsDeBusqueda";
import type { LeadListado } from "./tipos";

const ID = "11111111-1111-4111-8111-111111111111";
const OSM = { fuente: "osm_overpass", texto: "© OpenStreetMap contributors", url: "https://www.openstreetmap.org/copyright" };
const lead = (n: number, extra: Partial<LeadListado> = {}): LeadListado => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`, nombre: `Empresa ${n} SAS`, tipo_titular: "juridica",
  fuentes: ["osm_overpass"], licencias: ["ODbL 1.0"], ciudad: "Bogotá", tiene_web: true, tiene_telefono: null,
  tiene_email: null, ...extra,
});
const pagina = (items: LeadListado[], extra = {}) => ({
  items, total: items.length, pagina: 1, tamano: 25, atribuciones: [OSM], ...extra,
});

async function montar(respuesta: ReturnType<typeof pagina>, idioma = "es") {
  server.use(http.get("*/busquedas/:id/leads", () => HttpResponse.json(respuesta)));
  await i18n.changeLanguage(idioma);
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByRole("table")).toBeInTheDocument());
}

test("la juridica sale por su nombre y la natural como persona protegida", async () => {
  await montar(pagina([lead(1), lead(2, { nombre: null, tipo_titular: "natural", tiene_web: false })]));
  expect(screen.queryByText("Empresa 1 SAS")).toBeInTheDocument();
  expect(screen.queryByText("Persona natural (datos protegidos)")).toBeInTheDocument();
});

test("natural en ingles", async () => {
  await montar(pagina([lead(2, { nombre: null, tipo_titular: "natural" })]), "en");
  expect(screen.queryByText(en.leads.natural_protegida)).toBeInTheDocument();
  expect(en.leads.natural_protegida).not.toBe(es.leads.natural_protegida);
});

test("muestra fuentes, ciudad, licencia y web, y no pinta columnas de contacto sin dato", async () => {
  await montar(pagina([lead(1)]));
  const fila = screen.getAllByRole("row")[1];
  expect(fila).toHaveTextContent("OpenStreetMap");
  expect(fila).toHaveTextContent("Bogotá");
  expect(fila).toHaveTextContent("ODbL 1.0");
  const encabezados = screen.getAllByRole("columnheader").map((h) => h.textContent);
  expect(encabezados).not.toContain("Teléfono");
  expect(encabezados).not.toContain("Correo");
  expect(encabezados).toContain("Sitio web");
});

test("con contacto booleano pinta Si/No y nunca un valor", async () => {
  await montar(pagina([lead(1, { tiene_telefono: true, tiene_email: false })]));
  const encabezados = screen.getAllByRole("columnheader").map((h) => h.textContent);
  expect(encabezados).toContain("Teléfono");
  const fila = screen.getAllByRole("row")[1];
  expect(within(fila).queryAllByText("Sí").length).toBeGreaterThan(0);
  expect(within(fila).queryAllByText("No").length).toBeGreaterThan(0);
});

test("pagina: pide la siguiente con tamano 25 y deshabilita Anterior en la primera", async () => {
  const pedidas: string[] = [];
  server.use(
    http.get("*/busquedas/:id/leads", ({ request }) => {
      const u = new URL(request.url);
      pedidas.push(`${u.searchParams.get("pagina")}/${u.searchParams.get("tamano")}`);
      const p = Number(u.searchParams.get("pagina"));
      return HttpResponse.json(pagina([lead(p)], { total: 30, pagina: p }));
    }),
  );
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByText("Empresa 1 SAS")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
  expect(screen.queryByText("Página 1 de 2")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));

  await waitFor(() => expect(screen.queryByText("Empresa 2 SAS")).toBeInTheDocument());
  expect(pedidas).toEqual(["1/25", "2/25"]);
  expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
});

test("las atribuciones de la API van al pie con su enlace", async () => {
  await montar(pagina([lead(1)]));
  expect(screen.getByRole("link", { name: OSM.texto })).toHaveAttribute("href", OSM.url);
});

test("sin atribuciones no hay pie", async () => {
  await montar(pagina([lead(1)], { atribuciones: [] }));
  expect(screen.queryByLabelText("Atribución de datos")).not.toBeInTheDocument();
});

test("busqueda sin leads", async () => {
  server.use(http.get("*/busquedas/:id/leads", () => HttpResponse.json(pagina([], { total: 0 }))));
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByText("Esta búsqueda no trajo leads.")).toBeInTheDocument());
});

test("404 muestra no encontrada", async () => {
  server.use(http.get("*/busquedas/:id/leads", () => HttpResponse.json({ detail: "no_encontrada" }, { status: 404 })));
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent("No se encontró la búsqueda."));
});

test("enriquecer_muestra_que_trabaja_y_despues_el_resumen_con_lo_que_queda", async () => {
  let llamadas = 0;
  server.use(
    http.post("*/busquedas/:id/enriquecer", async () => {
      llamadas += 1;
      await delay(50); // que se alcance a ver la píldora de trabajo
      return HttpResponse.json(llamadas === 1
        ? { procesados: 15, contactables: 6, clasificados: 0, sin_clasificar: 15, cortado: false, pendientes: 5 }
        : { procesados: 5, contactables: 2, clasificados: 0, sin_clasificar: 5, cortado: false, pendientes: 0 });
    }),
  );
  await montar(pagina([lead(1)]));

  fireEvent.click(screen.getByRole("button", { name: es.enriquecer.boton }));
  expect(await screen.findByRole("status", { name: es.enriquecer.trabajando })).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText(/15 procesados · 6 con contacto · quedan 5/)).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: es.enriquecer.seguir }));
  await waitFor(() => expect(screen.queryByText(/5 procesados · 2 con contacto · quedan 0/)).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: es.enriquecer.seguir })).not.toBeInTheDocument();
});
