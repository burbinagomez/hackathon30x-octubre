#!/usr/bin/env bash
# Rojo de check_imagen.sh (research.md R-docker): un caso por rama, con el motivo nombrado en la salida.
set -uo pipefail
cd "$(dirname "$0")"
fallos=0

debe_fallar() { # imagen max_mb motivo...
  local imagen=$1 max_mb=$2 salida
  shift 2
  if salida=$(./check_imagen.sh "$imagen" "$max_mb" 2>&1); then
    echo "FALLA: $imagen con $max_mb MB pasó y tenía que fallar"
    fallos=$((fallos + 1))
    return
  fi
  for motivo in "$@"; do
    if ! grep -q -- "$motivo" <<<"$salida"; then
      echo "FALLA: $imagen con $max_mb MB no nombra '$motivo'. Salida: $salida"
      fallos=$((fallos + 1))
    fi
  done
}

docker pull -q python:3.12-slim >/dev/null
docker pull -q node:22-alpine >/dev/null

debe_fallar python:3.12-slim 250 pip root
debe_fallar node:22-alpine 250 node npm
debe_fallar python:3.12-slim 1 tamaño

if ((fallos > 0)); then
  echo "$fallos fallo(s)"
  exit 1
fi
echo "ok: los tres casos fallan nombrando su motivo"
