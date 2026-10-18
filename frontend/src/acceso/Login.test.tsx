import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import i18n from "../i18n";
import { boton, campo, espiarFijarIdioma } from "../test/fixtures";
import { server } from "../test/servidor";
import Login from "./Login";

function enviar(email: string, clave: string) {
  fireEvent.change(campo("Correo"), { target: { value: email } });
  fireEvent.change(campo("Clave"), { target: { value: clave } });
  fireEvent.click(boton("Ingresar"));
}

test("selector_sin_sesion_no_guarda", async () => {
  const patches = espiarFijarIdioma();
  render(<Login />);

  fireEvent.change(campo("Idioma"), { target: { value: "en" } });

  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Sign in" })).toBeInTheDocument(),
  );
  // Un PATCH sin sesión llegaría al handler tras un par de ticks: se le da el tiempo de llegar.
  await new Promise((r) => setTimeout(r, 50));
  expect(patches).toEqual([]);
  expect(sessionStorage.getItem("idioma_usuario")).toBeNull();
});

test("login_guarda_la_sesion_y_va_a_nueva_busqueda", async () => {
  let recibido: unknown;
  server.use(
    http.post("*/auth/sesion", async ({ request }) => {
      recibido = await request.json();
      return HttpResponse.json({ token: "jwt-1", idioma_usuario: "en", idioma_tenant: "es" });
    }),
  );
  render(<Login />);

  enviar("ana@ejemplo.test", "clave-de-prueba");

  await waitFor(() => expect(sessionStorage.getItem("token")).toBe("jwt-1"));
  expect(recibido).toEqual({ email: "ana@ejemplo.test", clave: "clave-de-prueba" });
  expect(sessionStorage.getItem("idioma_usuario")).toBe("en");
  expect(sessionStorage.getItem("idioma_tenant")).toBe("es");
  expect(location.pathname).toBe("/busqueda/nueva");
  expect(i18n.language).toBe("en");
});

test("credenciales_invalidas_muestran_error_y_no_guardan", async () => {
  server.use(http.post("*/auth/sesion", () => new HttpResponse(null, { status: 401 })));
  render(<Login />);

  enviar("ana@ejemplo.test", "mala");

  await waitFor(() =>
    expect(screen.queryByRole("alert")).toHaveTextContent("Correo o clave incorrectos"),
  );
  expect(sessionStorage.getItem("token")).toBeNull();
  expect(location.pathname).toBe("/");
});
