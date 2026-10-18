# Stack local con Docker

Levanta en tu máquina **Postgres + migraciones + api + web**, igual que CI prepara la base. Sirve para validar
cuando el deploy de web no está disponible. Prod no se toca: el login sigue siendo el Supabase Auth del proyecto.

1. `cp local/.env.example local/.env` y completá:
   - `SUPABASE_PUBLISHABLE_KEY`: la misma que tiene web (empieza con `sb_publishable_`).
   - `LOCAL_AUTH_USER_ID`: tu User UID de Supabase (Authentication → Users).
   - `CIFRADO_KEY`: `openssl rand -base64 32` (una nueva, solo local).
   - Opcionales: `IA_API_KEY` + `IA_MODELO` (Puerta B), `CROMA_API_KEY`, `TYPESAFE_*`.
2. Desde la raíz del repo:
   `docker compose -f local/docker-compose.yml --env-file local/.env up --build`
3. Abrí **http://localhost:8080** (web), **http://localhost:8000/docs** (api). Postgres queda en `localhost:5433`.

- La base local arranca vacía (tenant "Local"): corré una búsqueda para tener leads.
- `docker compose -f local/docker-compose.yml down` la frena; con `down -v` también borra la base.
- `local/.env` está en `.gitignore`: nunca lo subas ni pegues sus valores en un chat.
