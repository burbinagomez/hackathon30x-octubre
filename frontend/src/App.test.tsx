import { render, screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test } from "vitest";
import App from "./App";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test("muestra estado de la API", async () => {
  server.use(
    http.get("*/health", () => HttpResponse.json({ status: "ok", db: "ok" })),
  );
  render(<App />);
  expect(await screen.findByText("API: ok · DB: ok")).toBeInTheDocument();
});

test("sin respuesta todavía no muestra ok", async () => {
  server.use(http.get("*/health", () => delay("infinite")));
  render(<App />);
  expect(screen.queryByText(/ok/)).not.toBeInTheDocument();
});

test("con la llamada caída muestra API: error", async () => {
  server.use(http.get("*/health", () => HttpResponse.error()));
  render(<App />);
  expect(await screen.findByText(/API: error/)).toBeInTheDocument();
});

test("con db distinto de ok muestra DB: error", async () => {
  server.use(
    http.get("*/health", () =>
      HttpResponse.json({ status: "error", db: "error" }),
    ),
  );
  render(<App />);
  expect(await screen.findByText(/DB: error/)).toBeInTheDocument();
});
