import { vi } from "vitest";

/** Doble de @supabase/supabase-js: guarda una sesión en memoria y no toca la red. */
type SesionFalsa = { access_token: string } | null;
type ErrorAuth = { code: string; status: number } | null;

export const estado: { sesion: SesionFalsa; errorLogin: ErrorAuth; tokenAlIngresar: string } = {
  sesion: null,
  errorLogin: null,
  tokenAlIngresar: "jwt-supabase",
};

export const auth = {
  getSession: vi.fn(async () => ({ data: { session: estado.sesion }, error: null })),
  signInWithPassword: vi.fn(async (_credenciales: { email: string; password: string }) => {
    if (estado.errorLogin) return { data: { session: null }, error: estado.errorLogin };
    estado.sesion = { access_token: estado.tokenAlIngresar };
    return { data: { session: estado.sesion }, error: null };
  }),
  signOut: vi.fn(async () => {
    estado.sesion = null;
    return { error: null };
  }),
};

export const moduloFalso = { createClient: () => ({ auth }) };

export function reiniciarSupabase() {
  estado.sesion = null;
  estado.errorLogin = null;
  estado.tokenAlIngresar = "jwt-supabase";
  auth.getSession.mockClear();
  auth.signInWithPassword.mockClear();
  auth.signOut.mockClear();
}
