#!/usr/bin/env bash
# Job `imagenes` (research.md R-docker): la imagen final no trae node/npm/uv/pip, no corre como root
# y no pasa de max_mb. Reporta cada motivo, no solo el primero.
set -euo pipefail
imagen=${1:?uso: check_imagen.sh <imagen> <max_mb>}
max_mb=${2:?uso: check_imagen.sh <imagen> <max_mb>}
motivos=()

corre() {
  docker run --rm --entrypoint sh "$imagen" -c "$1" >/dev/null 2>&1
}

for binario in node npm uv; do
  if corre "command -v $binario"; then motivos+=("$binario"); fi
done
if corre "command -v pip || command -v pip3 || python -m pip --version"; then motivos+=("pip"); fi

usuario=$(docker image inspect --format '{{.Config.User}}' "$imagen")
if [[ -z $usuario || $usuario == root || $usuario == 0 || $usuario == 0:* || $usuario == root:* ]]; then
  motivos+=("root")
fi

# Suma de capas descomprimidas: .Size da el comprimido con el store de containerd y el descomprimido sin él.
mb=$(docker history -H=false --format '{{.Size}}' "$imagen" | awk '{s += $1} END {print int(s / 1048576)}')
if ((mb > max_mb)); then motivos+=("tamaño ${mb} MB > ${max_mb} MB"); fi

if ((${#motivos[@]} > 0)); then
  printf '%s falla:\n' "$imagen" >&2
  printf '  - %s\n' "${motivos[@]}" >&2
  exit 1
fi
echo "$imagen ok (${mb} MB de ${max_mb})"
