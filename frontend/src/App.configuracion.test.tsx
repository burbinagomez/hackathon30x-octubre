import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

// El módulo de supabase se evalúa al importar: hay que resetear antes de montar la App con otra configuración.
async function montar(key: string) {
  vi.resetModules();
  vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", key);
  await import("./i18n");
  const { createClient } = await import("@supabase/supabase-js");
  // Si la carga rompe, no hay nada que montar: el test falla en la aserción y no en el import.
  const App = await import("./App").then((m) => m.default, () => null);
  if (App) render(<App />);
  return createClient;
}

test("con_la_key_invalida_la_app_muestra_configuracion_incompleta_y_no_crea_el_cliente", async () => {
  sessionStorage.setItem("idioma_usuario", "es");
  const createClient = await montar("");
  expect(await screen.findByText("Configuración incompleta")).toBeInTheDocument();
  expect(createClient).not.toHaveBeenCalled();
});

test("con_la_key_invalida_el_mensaje_sale_en_ingles", async () => {
  sessionStorage.setItem("idioma_tenant", "en");
  await montar("sb_" + "secret_abcdefghijkl");
  expect(await screen.findByText("Incomplete configuration")).toBeInTheDocument();
});

test("con_la_key_valida_no_aparece_el_mensaje", async () => {
  await montar("sb_publishable_abcdefghijkl");
  expect(screen.queryByText("Configuración incompleta")).not.toBeInTheDocument();
});
