import { render, screen } from "@testing-library/react";
import { http } from "msw";
import { expect, test } from "vitest";
import es from "../i18n/es.json";
import ListaBusquedas from "../leads/ListaBusquedas";
import Tablero from "../tablero/Tablero";
import { server } from "../test/servidor";
import Esqueleto from "./Esqueleto";

const nunca = () => new Promise<Response>(() => undefined);

test("el_esqueleto_anuncia_que_carga_y_sus_barras_son_decorativas", () => {
  const { container } = render(<Esqueleto filas={3} />);
  expect(screen.getByRole("status")).toHaveTextContent(es.comun.cargando);
  expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  const barras = container.querySelectorAll(".esqueleto");
  expect(barras).toHaveLength(3);
  barras.forEach((b) => expect(b).toHaveAttribute("aria-hidden", "true"));
});

test("el_tablero_muestra_el_esqueleto_mientras_carga", async () => {
  server.use(http.get("*/tablero/fuentes", nunca), http.get("*/calificaciones/cpql", nunca));
  render(<Tablero />);
  expect(await screen.findByRole("status")).toHaveTextContent(es.comun.cargando);
});

test("la_lista_de_busquedas_muestra_el_esqueleto_mientras_carga", async () => {
  server.use(http.get("*/busquedas", nunca));
  render(<ListaBusquedas />);
  expect(await screen.findByRole("status")).toHaveTextContent(es.comun.cargando);
});
