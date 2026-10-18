import { createClient } from "@supabase/supabase-js";

// Solo la publishable key, que es pública por diseño (constitución 2.0.0). Nunca una secret.
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
);
