import { setupServer } from "msw/node";

// Sin handlers: cada test declara los suyos con server.use(...).
export const server = setupServer();
