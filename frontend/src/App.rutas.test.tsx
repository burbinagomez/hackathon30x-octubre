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

test("/costos?busqueda_id= muestra el libro filtrado; un id invalido no se manda", async () => {
  const pedidos: string[] = [];
  server.use(http.get("*/costos", ({ request }) => {
    pedidos.push(new URL(request.url).search);
    return HttpResponse.json({ items: [], total: 0, pagina: 1, tamano: 50, total_usd: "0", total_real_usd: "0", por_tipo: [], por_fuente: [] });
  }));
  history.replaceState(null, "", `/costos?busqueda_id=${ID}`);
  const { unmount } = render(<App />);
  await waitFor(() => expect(screen.queryByRole("heading", { level: 1, name: "Libro de costos" })).toBeInTheDocument());
  expect(pedidos).toEqual([`?pagina=1&busqueda_id=${ID}`]);
  unmount();
  history.replaceState(null, "", "/costos?busqueda_id=../x");
  render(<App />);
  await waitFor(() => expect(pedidos).toHaveLength(2));
  expect(pedidos[1]).toBe("?pagina=1");
});
