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
   y Postgres en `localhost:5433` (usuario `postgres`, clave `POSTGRES_PASSWORD` de tu `local/.env`).

Cómo funciona el login: `auth-local` imita lo mínimo de Supabase Auth (login, refresco y JWKS) con tu único usuario;
firma tokens ES256 con una clave que nace en cada arranque (si lo reiniciás, volvés a entrar). La api los verifica
igual que en prod (firma, `aud`, `iss`, `exp`) y busca tu fila en `usuarios`, que `preparar-db` siembra sola.

- La base arranca vacía (tenant "Local"): corré una búsqueda para tener leads.
- `docker compose -f local/docker-compose.yml down` la frena; con `down -v` también borra la base.
- `local/.env` está en `.gitignore`: nunca lo subas ni pegues sus valores en un chat.

## Probar el envío en local

Completá en `local/.env` las variables de email (`SMTP_*`, `REMITENTE`, `BAJA_SECRET`, `URL_PRIVACIDAD` y
`EMAIL_PRUEBA_DESTINOS` con **tus** direcciones) y levantá de nuevo. Dejá `EMAIL_MODO` vacío: es `prueba`, y en prueba
solo sale mail a `EMAIL_PRUEBA_DESTINOS`, nunca a un lead. Sin `BAJA_SECRET`, la api arranca igual y `/baja` da 404.

Atajos (desde la raíz del repo):

    C="docker compose -f local/docker-compose.yml"
    $C exec db psql -U postgres -c "SELECT id, tenant_id FROM busquedas ORDER BY creado_en DESC LIMIT 1"

1. **Vista previa** (no manda nada): `$C exec api python -m app.cli enviar --tenant <tenant_id> --busqueda <id> --dry-run`
   Ves `modo: prueba`, `aprobados: N`, `a enviar: M` y un ejemplo del mail con `/baja/<token>` al pie.
   `a enviar` cuenta solo los aprobados cuya dirección está en `EMAIL_PRUEBA_DESTINOS`: con leads de una búsqueda
   real lo normal es `0`. `aprobados: 0` = la búsqueda no tiene `mensaje base` o ningún lead es jurídica con email.
2. **Envío**: lo mismo sin `--dry-run`. Ves `enviados: M` y te llega el mail; el enlace del pie abre
   `http://localhost:8000/baja/…`, que pide confirmar antes de dar de baja.
3. **Respuesta a mano**: con el id del contacto enviado
   (`$C exec db psql -U postgres -c "SELECT id FROM contactos WHERE estado = 'enviado'"`):
   `$C exec api python -m app.cli respondio --tenant <tenant_id> --contacto <contacto_id>` → `respondio: 1`.
   Si no se le envió, sale con error y no marca nada.
4. **Tasa**: `$C exec api python -m app.cli tasa-respuesta --tenant <tenant_id>`
   → `email: contactados=M respondieron=1 tasa=…` (`sin contactos` si el tenant no tiene ninguno).
