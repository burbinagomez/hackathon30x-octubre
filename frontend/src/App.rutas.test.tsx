import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import { server } from "./test/servidor";

// jsdom trae ['en-US']: sin esto la app arranca en inglés.
beforeEach(() => vi.spyOn(navigator, "languages", "get").mockReturnValue(["es-CO"]));
afterEach(() => vi.restoreAllMocks());

const ID = "11111111-1111-4111-8111-111111111111";

test("/busquedas muestra la lista", async () => {
  server.use(http.get("*/busquedas", () => HttpResponse.json({ items: [] })));
  history.replaceState(null, "", "/busquedas");
  render(<App />);
  await waitFor(() => expect(screen.queryByRole("heading", { level: 1, name: "Búsquedas" })).toBeInTheDocument());
});

test("/busquedas/:id/leads muestra los leads de esa busqueda", async () => {
  let pedido = "";
  server.use(http.get("*/busquedas/:id/leads", ({ params }) => {
    pedido = String(params.id);
    return HttpResponse.json({ items: [], total: 0, pagina: 1, tamano: 25, atribuciones: [] });
  }));
  history.replaceState(null, "", `/busquedas/${ID}/leads`);
  render(<App />);
  await waitFor(() => expect(screen.queryByText("Esta búsqueda no trajo leads.")).toBeInTheDocument());
  expect(pedido).toBe(ID);
});

test("un id que no es uuid no es una ruta", async () => {
  server.use(http.get("*/health", () => HttpResponse.json({ status: "ok", db: "ok" })));
  history.replaceState(null, "", "/busquedas/../../tablero/leads");
  render(<App />);
  expect(await screen.findByText(/API:/)).toBeInTheDocument();
});

test("/leads?fuente= muestra los leads de esa fuente", async () => {
  let pedido = "";
  server.use(http.get("*/leads", ({ request }) => {
    pedido = new URL(request.url).searchParams.get("fuente") ?? "";
    return HttpResponse.json({ items: [], total: 0, pagina: 1, tamano: 25, atribuciones: [] });
  }));
  history.replaceState(null, "", "/leads?fuente=osm_overpass");
  render(<App />);
  await waitFor(() => expect(screen.queryByRole("heading", { level: 1, name: "Leads de OpenStreetMap" })).toBeInTheDocument());
  expect(pedido).toBe("osm_overpass");
});

test("/leads sin fuente muestra todos", async () => {
  server.use(http.get("*/leads", () => HttpResponse.json({ items: [], total: 0, pagina: 1, tamano: 25, atribuciones: [] })));
  history.replaceState(null, "", "/leads");
  render(<App />);
  await waitFor(() => expect(screen.queryByRole("heading", { level: 1, name: "Todos los leads" })).toBeInTheDocument());
});
