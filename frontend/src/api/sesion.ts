import { supabase } from "./supabase";

// El token lo guarda supabase-js; acá solo los idiomas (no son secretos) que trae GET /usuarios/me.
export type IdiomaGuardado = "es" | "en";

const CLAVES = { usuario: "idioma_usuario", tenant: "idioma_tenant" } as const;

export type Idiomas = { idiomaUsuario: IdiomaGuardado | null; idiomaTenant: IdiomaGuardado | null };

export type RespuestaUsuario = {
  idioma_usuario: IdiomaGuardado | null;
  idioma_tenant: IdiomaGuardado;
};

const comoIdioma = (valor: string | null): IdiomaGuardado | null =>
  valor === "es" || valor === "en" ? valor : null;

export function leerIdiomas(): Idiomas {
  return {
    idiomaUsuario: comoIdioma(sessionStorage.getItem(CLAVES.usuario)),
    idiomaTenant: comoIdioma(sessionStorage.getItem(CLAVES.tenant)),
  };
}

export function guardarIdiomas(r: RespuestaUsuario): void {
  sessionStorage.setItem(CLAVES.tenant, r.idioma_tenant);
  if (r.idioma_usuario) sessionStorage.setItem(CLAVES.usuario, r.idioma_usuario);
  else sessionStorage.removeItem(CLAVES.usuario);
}

export function fijarIdiomaUsuario(idioma: IdiomaGuardado): void {
  sessionStorage.setItem(CLAVES.usuario, idioma);
}

export async function tokenActual(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function cerrarSesion(): Promise<void> {
  await supabase.auth.signOut();
  for (const clave of Object.values(CLAVES)) sessionStorage.removeItem(clave);
}
