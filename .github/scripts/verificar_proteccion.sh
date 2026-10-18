#!/usr/bin/env bash
# Spec 012: lo corre el dueño del repo, porque el token de Actions no es admin y no ve esta config.
# Compara la protección real de main contra required-checks.txt, y verifica secret scanning con
# push protection prendidos y el default setup de CodeQL prendido (publica los checks Analyze required).
# Reporta cada motivo, no solo el primero. La salida se pega en docs/seguridad/revision-002-008.md.
set -euo pipefail
repo=${1:?uso: verificar_proteccion.sh <owner/repo>}
lista="$(dirname "$0")/../required-checks.txt"
mal=0
falla() { echo "FALLA $*"; mal=1; }

esperados=$(sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e '/^#/d' -e '/^$/d' "$lista" | sort -u)
if proteccion=$(gh api "repos/$repo/branches/main/protection"); then
  reales=$(jq -r '.required_status_checks.contexts[]?' <<<"$proteccion" | sed '/^$/d' | sort -u)
  while IFS= read -r c; do if [ -n "$c" ]; then falla "falta el required check: $c"; fi; done \
    < <(comm -23 <(printf '%s\n' "$esperados") <(printf '%s\n' "$reales"))
  while IFS= read -r c; do if [ -n "$c" ]; then falla "sobra el required check (no está en required-checks.txt): $c"; fi; done \
    < <(comm -13 <(printf '%s\n' "$esperados") <(printf '%s\n' "$reales"))
else
  falla "branches/main/protection: no se pudo leer (sin protección o sin permiso de admin)"
fi

if analisis=$(gh api "repos/$repo"); then
  for clave in secret_scanning secret_scanning_push_protection; do
    estado=$(jq -r --arg c "$clave" '.security_and_analysis[$c].status // "ausente"' <<<"$analisis")
    [ "$estado" = enabled ] || falla "$clave: $estado (tiene que ser enabled)"
  done
else
  falla "repos/$repo: no se pudo leer security_and_analysis"
fi

if setup=$(gh api "repos/$repo/code-scanning/default-setup"); then
  estado=$(jq -r '.state // "ausente"' <<<"$setup")
  [ "$estado" = configured ] || falla "code-scanning/default-setup: $estado (tiene que ser configured)"
else
  falla "code-scanning/default-setup: no se pudo leer"
fi

[ "$mal" = 0 ] && echo "OK: protección de main, secret scanning y CodeQL como dice la spec 012"
exit "$mal"
