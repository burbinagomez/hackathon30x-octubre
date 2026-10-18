import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import i18n from "../i18n";
import { server } from "./servidor";
import { reiniciarSupabase } from "./supabaseFalso";

// Ningún test habla con Supabase: el cliente real exige URL y key, y saldría a la red.
vi.mock("@supabase/supabase-js", async () => (await import("./supabaseFalso")).moduloFalso);

// Sin globals de vitest, Testing Library no limpia solo: los renders se acumulan entre tests.
afterEach(cleanup);

// Una llamada sin handler es un error del test, no un pasaje silencioso a la red.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(async () => {
  server.resetHandlers();
  reiniciarSupabase();
  // i18next y la URL son singletons: sin esto un test que cambió a en o navegó arrastra al siguiente.
  await i18n.changeLanguage("es");
  if (typeof history !== "undefined") history.replaceState(null, "", "/");
  // Los tests de arquitectura corren en node, sin DOM.
  if (typeof sessionStorage !== "undefined") sessionStorage.clear();
});
afterAll(() => server.close());
