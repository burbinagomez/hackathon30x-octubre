import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Sin globals de vitest, Testing Library no limpia solo: los renders se acumulan entre tests.
afterEach(cleanup);
