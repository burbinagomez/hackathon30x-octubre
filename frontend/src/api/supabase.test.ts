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
  let error: unknown;
  await cargar(key).catch((e) => (error = e));
  expect(error, "el módulo cargó con una key que no es publishable").toBeInstanceOf(Error);
  // El mensaje no repite el valor: un secreto no puede terminar en los logs.
  if (key) expect((error as Error).message).not.toContain(key);
});

test("acepta_una_key_publishable", async () => {
  const modulo = await cargar("sb_publishable_abcdefghijkl");
  expect(modulo.supabase).toBeDefined();
});
