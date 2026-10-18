import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import i18n from "../i18n";
import { server } from "../test/servidor";
import ListaBusquedas from "./ListaBusquedas";

const ID1 = "11111111-1111-4111-8111-111111111111";
const ID2 = "22222222-2222-4222-8222-222222222222";
const busqueda = (id: string, extra = {}) => ({
  id, creada_en: "2026-10-18T15:30:00+00:00", estado: "terminada", pais: "CO", departamento: "11", ciudad: "Bogotá",
  total_leads: 1234, ...extra,
});

async function montar(items: unknown[], idioma = "es") {
  server.use(http.get("*/busquedas", () => HttpResponse.json({ items })));
  await i18n.changeLanguage(idioma);
  render(<ListaBusquedas />);
}

test("cada busqueda enlaza a sus leads", async () => {
  await montar([busqueda(ID1), busqueda(ID2, { ciudad: null, departamento: null, total_leads: 0 })]);
  await waitFor(() => expect(screen.queryAllByRole("link", { name: /Colombia/ })).toHaveLength(2));
  const enlaces = screen.queryAllByRole("link", { name: /Colombia/ });
  expect(enlaces.map((e) => e.getAttribute("href"))).toEqual([`/busquedas/${ID1}/leads`, `/busquedas/${ID2}/leads`]);
  expect(enlaces[0]).toHaveTextContent("Bogotá");
});

test("muestra el total de leads y el estado, formateados al idioma", async () => {
  await montar([busqueda(ID1)], "en");
  await waitFor(() => expect(screen.queryByText(/1,234/)).toBeInTheDocument());
  expect(screen.queryByRole("heading", { level: 1 })).toHaveTextContent("Searches");
  expect(screen.queryByRole("link", { name: /Completed/ })).toBeInTheDocument();
});

test("sin busquedas lo dice", async () => {
  await montar([]);
  await waitFor(() => expect(screen.queryByText("Todavía no hay búsquedas.")).toBeInTheDocument());
});

test("si la API falla muestra el error", async () => {
  server.use(http.get("*/busquedas", () => new HttpResponse(null, { status: 500 })));
  render(<ListaBusquedas />);
  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent("No se pudieron cargar las búsquedas."));
});
