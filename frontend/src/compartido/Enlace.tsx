import type { ReactNode } from "react";
import { navegar } from "./navegar";

/** Enlace interno: href real (abrir en otra pestaña, accesibilidad) y navegación sin recargar al hacer clic normal. */
export default function Enlace({ a, children }: { a: string; children: ReactNode }) {
  return (
    <a
      href={a}
      onClick={(e) => {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        navegar(a);
      }}
    >
      {children}
    </a>
  );
}
