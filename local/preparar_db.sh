#!/usr/bin/env bash
# Prepara la base local como CI: idempotente, se puede correr en cada `up`.
set -euo pipefail
url="postgresql://postgres@db:5432/postgres"
psql=(psql "$url" -X -q -v ON_ERROR_STOP=1)

"${psql[@]}" -f /scripts/supabase_simulado.sql
"${psql[@]}" -f /scripts/roles.sql
# Las variables de psql (:'x') solo se interpolan leyendo de stdin o -f, no con -c.
"${psql[@]}" -v pw="$APP_RT_PASSWORD" <<<"ALTER ROLE app_rt PASSWORD :'pw';"
MIGRACIONES=/migrations bash /scripts/migrar_local.sh "$url"

# Tenant fijo y, si se dio, el usuario de Supabase Auth (su id está en el panel: Authentication > Users).
"${psql[@]}" -v t="$LOCAL_TENANT_ID" \
  <<<"INSERT INTO tenants (id, nombre, idioma) VALUES (:'t', 'Local', 'es') ON CONFLICT (id) DO NOTHING;"
if [[ -n "${LOCAL_AUTH_USER_ID:-}" ]]; then
  "${psql[@]}" -v u="$LOCAL_AUTH_USER_ID" -v t="$LOCAL_TENANT_ID" \
    <<<"INSERT INTO usuarios (auth_user_id, tenant_id, idioma) VALUES (:'u', :'t', 'es') ON CONFLICT (auth_user_id) DO NOTHING;"
  echo "usuario local listo"
else
  echo "AVISO: sin LOCAL_AUTH_USER_ID no vas a poder entrar (falta tu fila en usuarios)" >&2
fi
echo "base local lista"
