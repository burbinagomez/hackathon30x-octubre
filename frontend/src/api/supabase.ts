import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Solo la publishable key, que es pública por diseño (constitución 2.0.0). Nunca una secret ni una
// key legacy (JWT). Si la configuración no sirve no se crea el cliente (y nunca se imprime el valor):
// la app lo muestra como "Configuración incompleta" en vez de romper la carga con una pantalla en blanco.
const key: string = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
const url: string = import.meta.env.VITE_SUPABASE_URL ?? "";

export const configuracionValida: boolean = key.startsWith("sb_publishable_") && url !== "";

export const supabase: SupabaseClient | null = configuracionValida ? createClient(url, key) : null;
