// La sesión vive en sessionStorage (spec 005, Auth): sin cookies no hay CSRF.
export type IdiomaGuardado = "es" | "en";

const CLAVES = { token: "token", usuario: "idioma_usuario", tenant: "idioma_tenant" } as const;

export type Sesion = {
  token: string | null;
  idiomaUsuario: IdiomaGuardado | null;
  idiomaTenant: IdiomaGuardado | null;
};

export type RespuestaSesion = {
  token: string;
  idioma_usuario: IdiomaGuardado | null;
  idioma_tenant: IdiomaGuardado;
};

const comoIdioma = (valor: string | null): IdiomaGuardado | null =>
  valor === "es" || valor === "en" ? valor : null;

export function leerSesion(): Sesion {
  return {
    token: sessionStorage.getItem(CLAVES.token),
    idiomaUsuario: comoIdioma(sessionStorage.getItem(CLAVES.usuario)),
    idiomaTenant: comoIdioma(sessionStorage.getItem(CLAVES.tenant)),
  };
}

export function guardarSesion(r: RespuestaSesion): void {
  sessionStorage.setItem(CLAVES.token, r.token);
  sessionStorage.setItem(CLAVES.tenant, r.idioma_tenant);
  if (r.idioma_usuario) sessionStorage.setItem(CLAVES.usuario, r.idioma_usuario);
  else sessionStorage.removeItem(CLAVES.usuario);
}

export function fijarIdiomaUsuario(idioma: IdiomaGuardado): void {
  sessionStorage.setItem(CLAVES.usuario, idioma);
}

export function borrarSesion(): void {
  for (const clave of Object.values(CLAVES)) sessionStorage.removeItem(clave);
}
