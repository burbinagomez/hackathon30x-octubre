# Stack local con Docker

Levanta en tu máquina **Postgres + migraciones + auth local + api + web**, sin depender de ningún servicio externo
para entrar. Sirve para validar cuando el deploy no está disponible. Prod no se toca.

1. `cp local/.env.example local/.env` y completá:
   - `LOCAL_EMAIL` y `LOCAL_PASSWORD`: tu usuario local (el único).
   - `CIFRADO_KEY`: `openssl rand -base64 32` (una nueva, solo local).
   - Opcionales: `IA_API_KEY` + `IA_MODELO` (Puerta B), `CROMA_API_KEY`, `TYPESAFE_*`.
2. Desde la raíz del repo:
   `docker compose -f local/docker-compose.yml --env-file local/.env up --build`
3. Abrí **http://localhost:8080** y entrá con ese email y contraseña. La api está en **http://localhost:8000/docs**
   y Postgres en `localhost:5433` (usuario `postgres`, clave `postgres-local`).

Cómo funciona el login: `auth-local` imita lo mínimo de Supabase Auth (login, refresco y JWKS) con tu único usuario;
firma tokens ES256 con una clave que nace en cada arranque (si lo reiniciás, volvés a entrar). La api los verifica
igual que en prod (firma, `aud`, `iss`, `exp`) y busca tu fila en `usuarios`, que `preparar-db` siembra sola.

- La base arranca vacía (tenant "Local"): corré una búsqueda para tener leads.
- `docker compose -f local/docker-compose.yml down` la frena; con `down -v` también borra la base.
- `local/.env` está en `.gitignore`: nunca lo subas ni pegues sus valores en un chat.
