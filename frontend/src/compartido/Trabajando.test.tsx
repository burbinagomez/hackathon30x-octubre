import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Trabajando from "./Trabajando";

afterEach(() => vi.useRealTimers());

test("anuncia_que_trabaja_con_su_texto_y_un_cronometro", () => {
  vi.useFakeTimers();
  render(<Trabajando texto="Consultando las fuentes" />);

  const estado = screen.getByRole("status");
  expect(estado).toHaveTextContent("Consultando las fuentes");
  expect(estado).toHaveTextContent("0:00");
  act(() => vi.advanceTimersByTime(17_000));
  expect(estado).toHaveTextContent("0:17");
  act(() => vi.advanceTimersByTime(60_000));
  expect(estado).toHaveTextContent("1:17");
});

test("el_anillo_es_decorativo_para_el_lector_de_pantalla", () => {
  const { container } = render(<Trabajando texto="x" />);
  const anillo = container.querySelector(".anillo");
  expect(anillo).not.toBeNull();
  expect(anillo).toHaveAttribute("aria-hidden", "true");
});

test("muestra_el_detalle_por_paso_si_lo_hay", () => {
  render(<Trabajando texto="Buscando" pasos={["OpenStreetMap", "RUES"]} />);
  expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["OpenStreetMap", "RUES"]);
});
