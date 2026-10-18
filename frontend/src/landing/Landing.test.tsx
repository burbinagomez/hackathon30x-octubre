import { render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";
import i18n from "../i18n";
import { estado } from "../test/supabaseFalso";
import Landing from "./Landing";

test("tiene un solo h1 y una seccion con h2 por bloque", () => {
  render(<Landing />);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.getByRole("heading", { level: 1, name: "Más leads, menor costo" })).toBeInTheDocument();
  for (const nombre of ["El problema", "La solución", "Lo que nadie más te muestra"]) {
    expect(screen.getByRole("heading", { level: 2, name: nombre })).toBeInTheDocument();
  }
  expect(screen.getByText("$80–500")).toBeInTheDocument();
  expect(screen.getByText("3 de 5")).toBeInTheDocument();
  expect(screen.getByText(/Arquitectura hexagonal/)).toBeInTheDocument();
});

test("sin sesion Empezar y Ver el tablero van a /login", async () => {
  render(<Landing />);
  const empezar = screen.getAllByRole("link", { name: "Empezar" });
  expect(empezar.length).toBeGreaterThanOrEqual(2);
  await waitFor(() => expect(estado.sesion).toBeNull());
  for (const a of empezar) expect(a).toHaveAttribute("href", "/login");
  expect(screen.getByRole("link", { name: "Ver el tablero" })).toHaveAttribute("href", "/login");
});

test("con sesion Empezar va a /busqueda/nueva y el tablero a /tablero", async () => {
  estado.sesion = { access_token: "jwt" };
  render(<Landing />);
  await waitFor(() => expect(screen.getAllByRole("link", { name: "Empezar" })[0]).toHaveAttribute("href", "/busqueda/nueva"));
  expect(screen.getByRole("link", { name: "Ver el tablero" })).toHaveAttribute("href", "/tablero");
});

test("en inglés", async () => {
  await i18n.changeLanguage("en");
  render(<Landing />);
  expect(screen.getByRole("heading", { level: 1, name: "More leads, lower cost" })).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Get started" }).length).toBeGreaterThanOrEqual(2);
  expect(screen.getByRole("link", { name: "See the dashboard" })).toBeInTheDocument();
});

test.each(["es", "en"])("no promete WhatsApp ni email masivo (%s)", async (idioma) => {
  await i18n.changeLanguage(idioma);
  const { container } = render(<Landing />);
  expect(within(container).getByRole("heading", { level: 1 })).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/whatsapp|email masivo|mass email|bulk email/i);
});
