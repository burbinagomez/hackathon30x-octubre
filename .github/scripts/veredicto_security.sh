#!/usr/bin/env bash
# Gate fail-closed de revision-seguridad (spec 012): lee el reporte del agente `security` por stdin.
# Sale 0 solo si, fuera de bloques de código, hay exactamente una línea "Veredicto:" y es
# "Veredicto: PASA" o "Veredicto: PASA CON OBSERVACIONES". Cualquier otra cosa bloquea.
set -euo pipefail

veredictos=$(awk '
  { sub(/\r$/, "") }
  /^ ? ? ?(```|~~~)/ { cerco = !cerco; next }
  cerco || /^(    |\t)/ { next }
  /^ ? ? ?Veredicto:/ { print }
')

# Con dos líneas, $veredictos lleva un salto y no coincide con ninguna.
case "$veredictos" in
  "Veredicto: PASA" | "Veredicto: PASA CON OBSERVACIONES") exit 0 ;;
esac
echo "revision-seguridad BLOQUEA: se esperaba una sola línea 'Veredicto: PASA' o 'Veredicto: PASA CON OBSERVACIONES'" >&2
exit 1
