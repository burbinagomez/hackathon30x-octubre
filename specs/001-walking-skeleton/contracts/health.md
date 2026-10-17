# Contrato — `GET /health`

| Caso | Status | Body |
|---|---|---|
| DB responde a `SELECT 1` | 200 | `{"status":"ok","db":"ok"}` |
| DB no responde | 503 | `{"status":"error","db":"error"}` |

- Sin auth. Sin datos del entorno ni del error en el body (nada de mensajes de excepción).
- CORS: solo orígenes en `CORS_ORIGINS`.

Front: `App` llama `${VITE_API_URL}/health` y muestra `API: ok · DB: ok`; si falla la llamada, `API: error`; si `db` ≠ ok, `DB: error`.
