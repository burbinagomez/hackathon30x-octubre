import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import Login from "./acceso/Login";
import NuevaBusqueda from "./busqueda/NuevaBusqueda";
import SelectorIdioma from "./compartido/SelectorIdioma";
import { respuestaTablero } from "./test/fixtures";
import { server } from "./test/servidor";
import Tablero from "./tablero/Tablero";

// Por glob, como marca.test.ts: si falta el archivo, el rojo es una aserción y no un error de resolución.
const hojas = import.meta.glob<string>("./estilos.css", {
  query: "?raw",
  import: "default",
  eager: true,
});
const main = import.meta.glob<string>("./main.tsx", { query: "?raw", import: "default", eager: true });

function css(): string {
  expect(Object.keys(hojas)).toContain("./estilos.css");
  const texto = hojas["./estilos.css"];
  expect(texto.length).toBeGreaterThan(0);
  return texto.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** El cuerpo de la primera regla cuyo selector contiene `selector` como elemento de una lista. */
function regla(selector: string): string {
  const reglas = [...css().matchAll(/([^{}]+)\{([^}]*)\}/g)];
  const r = reglas.find(([, sel]) => sel.split(",").some((s) => s.trim() === selector));
  expect(r, `no hay regla para ${selector}`).toBeDefined();
  return r![2];
}

test("estilos.css se importa en main.tsx", () => {
  expect(main["./main.tsx"]).toMatch(/import\s+["']\.\/estilos\.css["']/);
});

test.each(["button", "input", "select", "textarea"])("%s mide al menos 44px de alto", (el) => {
  const alto = regla(el).match(/min-height:\s*(\d+)px/);
  expect(Number(alto?.[1])).toBeGreaterThanOrEqual(44);
});

test("hay estado de foco visible", () => {
  expect(css()).toMatch(/:focus-visible\s*\{[^}]*outline:/);
});

test("los estilos usan variables de tokens y la tabla scrollea en su contenedor", () => {
  expect(css()).toMatch(/var\(--color-oscuro\)/);
  expect(regla(".tabla-scroll")).toMatch(/overflow-x:\s*auto/);
  // Mobile-first: solo min-width.
  expect(css()).not.toMatch(/max-width\s*:\s*\d+px\)/);
});

test("el lima solo va de fondo, nunca como color de texto", () => {
  expect(css()).not.toMatch(/(^|[;{\s])color:\s*var\(--color-acento\)/);
});

test("estilos.css usa los tokens semánticos y no las variables de marca para superficie, texto o borde", () => {
  const texto = css();
  for (const t of ["superficie", "texto", "borde", "acento-texto", "foco"]) {
    expect(texto, t).toMatch(new RegExp(`var\\(--color-${t}\\)`));
  }
  expect(texto).not.toMatch(/(background|color|border[a-z-]*):[^;]*var\(--color-(fondo|gris|blanco)\)/);
  expect(texto).not.toMatch(/(^|[;{\s])(color|outline):[^;]*var\(--color-oscuro\)/);
  expect(texto).not.toMatch(/#[0-9a-f]{3,8}\b/i);
});

test("login: card centrada con labels asociados a sus inputs", () => {
  const { container } = render(<Login />);
  expect(container.querySelector("main.pantalla.pantalla-tarjeta")).not.toBeNull();
  for (const etiqueta of ["Correo", "Clave"]) {
    const campo = screen.getByLabelText(etiqueta);
    expect(campo.tagName).toBe("INPUT");
  }
  expect(screen.getByRole("button", { name: "Ingresar" })).toHaveClass("boton");
});

test("selector de idioma lleva su clase", () => {
  render(<SelectorIdioma />);
  expect(screen.getByLabelText("Idioma")).toHaveClass("selector-idioma");
});

test("nueva búsqueda: pantalla, campos con clase y botones con clase", () => {
  const { container } = render(<NuevaBusqueda />);
  expect(container.querySelector("main.pantalla")).not.toBeNull();
  expect(container.querySelectorAll(".campo").length).toBeGreaterThanOrEqual(9);
  for (const b of screen.getAllByRole("button")) expect(b).toHaveClass("boton");
});

test("nueva búsqueda: el ancho de cada campo es una clase explícita, nunca la posición", () => {
  expect(css()).not.toMatch(/nth-child/);
  expect(regla(".campo-ancho")).toMatch(/grid-column:\s*1\s*\/\s*-1/);
  // Espaciado parejo: el mismo token entre campos y entre bloques.
  for (const sel of [".formulario-ancho", ".grupo"]) expect(regla(sel), sel).toMatch(/gap:\s*var\(--espacio\)/);
  expect(regla(".acciones-fin")).toMatch(/justify-content:\s*flex-end/);
});

test("tablero sin datos (API caída) igual muestra título y un estado", async () => {
  server.use(http.get("*/tablero/fuentes", () => HttpResponse.error()));
  render(<Tablero />);
  expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
});

test("tablero con datos: tabla en su contenedor y métricas", async () => {
  server.use(http.get("*/tablero/fuentes", () => HttpResponse.json(respuestaTablero())));
  const { container } = render(<Tablero />);
  await screen.findByRole("table");
  expect(container.querySelector(".tabla-scroll table")).not.toBeNull();
  expect(container.querySelectorAll(".metricas .metrica").length).toBe(2);
});
