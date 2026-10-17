#!/usr/bin/env bash
# Aplica supabase/migrations/*.sql en orden, como superusuario: lo mismo que `supabase db push`
# (que corre como postgres) hace en prod. Solo local y CI; prod migra por el job `migrar`.
# Registra lo aplicado en supabase_migrations.schema_migrations, como el CLI: no se reaplica.
set -euo pipefail
shopt -s nullglob

url="${1:?uso: migrar_local.sh <url de superusuario>}"
dir="$(cd "${MIGRACIONES:-$(dirname "$0")/../../supabase/migrations}" && pwd)"
psql=(psql "$url" -X -q -v ON_ERROR_STOP=1)

"${psql[@]}" -c "CREATE SCHEMA IF NOT EXISTS supabase_migrations" \
  -c "CREATE TABLE IF NOT EXISTS supabase_migrations.schema_migrations (version text PRIMARY KEY, name text)"

for f in "$dir"/*.sql; do
  base="$(basename "$f" .sql)"
  # El mismo patrón que el CLI; además deja version y name seguros para interpolar en SQL.
  [[ "$base" =~ ^([0-9]+)_([a-z0-9_]+)$ ]] || { echo "migrar_local: nombre inválido $f" >&2; exit 1; }
  version="${BASH_REMATCH[1]}" nombre="${BASH_REMATCH[2]}"
  [[ -z "$("${psql[@]}" -tA -c "SELECT 1 FROM supabase_migrations.schema_migrations WHERE version = '$version'")" ]] || continue
  # -1: el archivo y su registro en una transacción; si falla, no queda nada a medias.
  "${psql[@]}" -1 -f "$f" \
    -c "INSERT INTO supabase_migrations.schema_migrations (version, name) VALUES ('$version', '$nombre')" \
    || { echo "migrar_local: falló $f" >&2; exit 1; }
  echo "aplicada $base"
done
