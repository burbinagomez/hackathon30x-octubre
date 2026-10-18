import { http, HttpResponse } from "msw";
import { afterEach, expect, test, vi } from "vitest";
import { iniciarSesion } from "../test/fixtures";
import { server } from "../test/servidor";
import { auth, estado } from "../test/supabaseFalso";
import { pedir } from "./cliente";

afterEach(() => vi.unstubAllGlobals());

function espiarNavegacion() {
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
  return assign;
}

test("manda_el_token_como_bearer", async () => {
  iniciarSesion();
  let autorizacion: string | null = null;
  server.use(
    http.get("*/actividades", ({ request }) => {
      autorizacion = request.headers.get("authorization");
      return HttpResponse.json([]);
    }),
  );
  await pedir("/actividades");
  expect(autorizacion).toBe("Bearer jwt-de-prueba");
});

test("un_401_lleva_al_login_y_borra_el_token", async () => {
  iniciarSesion();
  const assign = espiarNavegacion();
  server.use(http.get("*/tablero/fuentes", () => new HttpResponse(null, { status: 401 })));

  await pedir("/tablero/fuentes").catch(() => undefined);

  expect(assign).toHaveBeenCalledWith("/login");
  expect(auth.signOut).toHaveBeenCalled();
  expect(estado.sesion).toBeNull();
});

test("un_401_sin_sesion_no_redirige_y_falla", async () => {
  // Sin sesión, redirigir a /login recargaría la pantalla donde ya está.
  const assign = espiarNavegacion();
  server.use(http.get("*/usuarios/me", () => new HttpResponse(null, { status: 401 })));

  await expect(pedir("/usuarios/me")).rejects.toMatchObject({
    estado: 401,
  });
  expect(assign).not.toHaveBeenCalled();
});
