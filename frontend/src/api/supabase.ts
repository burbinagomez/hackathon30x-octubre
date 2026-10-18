import { createClient } from "@supabase/supabase-js";

// Solo la publishable key, que es pública por diseño (constitución 2.0.0). Nunca una secret ni una
// key legacy (JWT). Falla al cargar y sin imprimir el valor.
const key: string = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
if (!key.startsWith("sb_publishable_")) {
  throw new Error("VITE_SUPABASE_PUBLISHABLE_KEY tiene que ser una key sb_publishable_");
}

export const supabase = createClient(import.meta.env.VITE_SUPABASE_URL, key);
