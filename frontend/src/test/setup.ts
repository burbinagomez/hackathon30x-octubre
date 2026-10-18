import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./servidor";

// Sin globals de vitest, Testing Library no limpia solo: los renders se acumulan entre tests.
afterEach(cleanup);

// Una llamada sin handler es un error del test, no un pasaje silencioso a la red.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  // Los tests de arquitectura corren en node, sin DOM.
  if (typeof sessionStorage !== "undefined") sessionStorage.clear();
});
afterAll(() => server.close());
