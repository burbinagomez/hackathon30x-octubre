import { afterEach, expect, test, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

// Armado en runtime: un JWT anon escrito en src/ lo atraparía sin_secretos.test.ts.
function jwtLegacy() {
  const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${b64({ alg: "HS256" })}.${b64({ role: "anon" })}.firma`;
}

async function cargar(key: string | undefined) {
  vi.resetModules();
  if (key !== undefined) vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", key);
  else vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "");
  return import("./supabase");
}

test.each([
  ["jwt legacy anon", jwtLegacy()],
  ["secret key", "sb_" + "secret_abcdefghijkl"],
  ["vacía", ""],
])("rechaza_una_key_que_no_es_publishable[%s]", async (_caso, key) => {
  const aviso = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const modulo = await cargar(key).catch(() => ({}) as Partial<Awaited<ReturnType<typeof cargar>>>);
  // El módulo ya no rompe la carga (pantalla en blanco): declara la configuración inválida y no crea el cliente.
  expect(modulo.configuracionValida).toBe(false);
  expect(modulo.supabase).toBeNull();
  const { createClient } = await import("@supabase/supabase-js");
  expect(createClient).not.toHaveBeenCalled();
  // Nada imprime el valor: un secreto no puede terminar en los logs.
  if (key) expect(JSON.stringify(aviso.mock.calls)).not.toContain(key);
  aviso.mockRestore();
});

test("sin_url_de_supabase_tampoco_crea_el_cliente", async () => {
  vi.stubEnv("VITE_SUPABASE_URL", "");
  const modulo = await cargar("sb_publishable_abcdefghijkl").catch(() => ({}) as Partial<Awaited<ReturnType<typeof cargar>>>);
  expect(modulo.configuracionValida).toBe(false);
  expect(modulo.supabase).toBeNull();
});

test("acepta_una_key_publishable", async () => {
  const modulo = await cargar("sb_publishable_abcdefghijkl");
  expect(modulo.configuracionValida).toBe(true);
  expect(modulo.supabase).not.toBeNull();
});
