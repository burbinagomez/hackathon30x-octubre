import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import i18n from "../i18n";
import { boton, campo, espiarFijarIdioma } from "../test/fixtures";
import { server } from "../test/servidor";
import { auth, estado } from "../test/supabaseFalso";
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

test("login_con_supabase_pide_usuarios_me", async () => {
  let autorizacion: string | null = null;
  server.use(
    http.get("*/usuarios/me", ({ request }) => {
      autorizacion = request.headers.get("authorization");
      return HttpResponse.json({ idioma_usuario: "en", idioma_tenant: "es" });
    }),
  );
  render(<Login />);

  enviar("ana@ejemplo.test", "clave-de-prueba");

  await waitFor(() => expect(location.pathname).toBe("/busqueda/nueva"));
  expect(auth.signInWithPassword).toHaveBeenCalledWith({
    email: "ana@ejemplo.test",
    password: "clave-de-prueba",
  });
  expect(autorizacion).toBe("Bearer jwt-supabase");
  // Los idiomas vienen de /usuarios/me, no del token.
  expect(sessionStorage.getItem("idioma_usuario")).toBe("en");
  expect(sessionStorage.getItem("idioma_tenant")).toBe("es");
  expect(i18n.language).toBe("en");
});

test("credenciales_invalidas_muestran_error_y_no_piden_usuarios_me", async () => {
  estado.errorLogin = { code: "invalid_credentials", status: 400 };
  let pedidos = 0;
  server.use(http.get("*/usuarios/me", () => (pedidos++, HttpResponse.json({}))));
  render(<Login />);

  enviar("ana@ejemplo.test", "mala");

  await waitFor(() =>
    expect(screen.queryByRole("alert")).toHaveTextContent("Correo o clave incorrectos"),
  );
  expect(pedidos).toBe(0);
  expect(location.pathname).toBe("/");
});

test("usuario_sin_fila_cierra_sesion", async () => {
  // Autenticado en Supabase pero sin fila en usuarios: la API da 403 y no puede quedar una sesión a medias.
  server.use(http.get("*/usuarios/me", () => new HttpResponse(null, { status: 403 })));
  render(<Login />);

  enviar("ana@ejemplo.test", "clave-de-prueba");

  await waitFor(() =>
    expect(screen.queryByRole("alert")).toHaveTextContent("No se pudo ingresar. Probá de nuevo."),
  );
  expect(auth.signOut).toHaveBeenCalled();
  expect(estado.sesion).toBeNull();
});

test("un_fallo_del_servidor_no_se_presenta_como_clave_mala", async () => {
  server.use(http.get("*/usuarios/me", () => new HttpResponse(null, { status: 500 })));
  render(<Login />);

  enviar("ana@ejemplo.test", "clave-de-prueba");

  await waitFor(() =>
    expect(screen.queryByRole("alert")).toHaveTextContent("No se pudo ingresar. Probá de nuevo."),
  );
});
