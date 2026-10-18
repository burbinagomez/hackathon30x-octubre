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

// El tipo no existe en runtime: lo que llega del servidor se valida antes de escribirlo.
function guardar(clave: string, valor: string | null): void {
  const idioma = comoIdioma(valor);
  if (idioma) sessionStorage.setItem(clave, idioma);
  else sessionStorage.removeItem(clave);
}

export function guardarIdiomas(r: RespuestaUsuario): void {
  guardar(CLAVES.tenant, r.idioma_tenant);
  guardar(CLAVES.usuario, r.idioma_usuario);
}

export function fijarIdiomaUsuario(idioma: IdiomaGuardado): void {
  guardar(CLAVES.usuario, idioma);
}

export async function tokenActual(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function cerrarSesion(): Promise<void> {
  await supabase.auth.signOut();
  for (const clave of Object.values(CLAVES)) sessionStorage.removeItem(clave);
}
