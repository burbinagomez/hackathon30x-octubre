import { render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import i18n from "../i18n";
import { server } from "../test/servidor";
import LeadsDeFuente from "./LeadsDeFuente";

const OSM = { fuente: "osm_overpass", texto: "© OpenStreetMap contributors", url: "https://www.openstreetmap.org/copyright" };
const respuesta = {
  items: [{ id: "00000000-0000-4000-8000-000000000001", nombre: "Acme SAS", tipo_titular: "juridica", fuentes: ["osm_overpass"],
    licencias: ["ODbL 1.0"], ciudad: "Bogotá", tiene_web: true, tiene_telefono: null, tiene_email: null }],
  total: 1, pagina: 1, tamano: 25, atribuciones: [OSM],
};

test("titulo con la fuente y pide /leads?fuente=", async () => {
  let pedido = "";
  server.use(http.get("*/leads", ({ request }) => {
    pedido = new URL(request.url).search;
    return HttpResponse.json(respuesta);
  }));
  render(<LeadsDeFuente fuente="osm_overpass" />);
  await waitFor(() => expect(screen.queryByText("Acme SAS")).toBeInTheDocument());
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Leads de OpenStreetMap");
  expect(pedido).toBe("?fuente=osm_overpass&pagina=1&tamano=25");
});

test("sin fuente pide todos y lo titula asi, en ingles tambien", async () => {
  let pedido = "";
  server.use(http.get("*/leads", ({ request }) => {
    pedido = new URL(request.url).search;
    return HttpResponse.json(respuesta);
  }));
  await i18n.changeLanguage("en");
  render(<LeadsDeFuente fuente={null} />);
  await waitFor(() => expect(screen.queryByText("Acme SAS")).toBeInTheDocument());
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("All leads");
  expect(pedido).toBe("?pagina=1&tamano=25");
});

test("la licencia del pie es externa", async () => {
  server.use(http.get("*/leads", () => HttpResponse.json(respuesta)));
  render(<LeadsDeFuente fuente="osm_overpass" />);
  await waitFor(() => expect(screen.queryByText("Acme SAS")).toBeInTheDocument());
  const pie = screen.getByLabelText("Atribución de datos");
  expect(pie).toHaveTextContent("Licencia");
  expect(within(pie).getByRole("link", { name: OSM.texto })).toHaveAttribute("target", "_blank");
});

test("fuente desconocida (422) muestra error", async () => {
  server.use(http.get("*/leads", () => HttpResponse.json({ errores: [{ campo: "fuente", codigo: "desconocida" }] }, { status: 422 })));
  render(<LeadsDeFuente fuente="otra" />);
  await waitFor(() => expect(screen.queryByRole("alert")).toBeInTheDocument());
});
