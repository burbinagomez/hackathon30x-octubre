import { cerrarSesion, tokenActual } from "./sesion";

export type Opciones = { metodo?: string; cuerpo?: unknown };

export class ErrorApi extends Error {
  constructor(readonly estado: number) {
    super(`HTTP ${estado}`);
  }
}

/** Cliente HTTP único. Un 401 con sesión la borra y lleva al login; sin sesión (login fallido) solo falla. */
export async function pedir<T>(ruta: string, { metodo, cuerpo }: Opciones = {}): Promise<T> {
  const token = await tokenActual();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (cuerpo !== undefined) headers["Content-Type"] = "application/json";

  const respuesta = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${ruta}`, {
    method: metodo,
    headers,
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });

  if (respuesta.status === 401 && token) {
    await cerrarSesion();
    window.location.assign("/login");
  }
  if (!respuesta.ok) throw new ErrorApi(respuesta.status);
  return respuesta.status === 204 ? (undefined as T) : ((await respuesta.json()) as T);
}
