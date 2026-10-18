import { cerrarSesion, tokenActual } from "./sesion";

export type Opciones = { metodo?: string; cuerpo?: unknown; /** Un archivo CSV como cuerpo crudo (text/csv), no JSON. */ csv?: Blob };

export class ErrorApi extends Error {
  constructor(readonly estado: number) {
    super(`HTTP ${estado}`);
  }
}

// Solo rutas de la API: empiezan con "/" y no con "//" ni "/\" (protocolo relativo), sin espacios ni controles.
const RUTA_API = /^\/(?![/\\])[^\s\\]*$/;

/** Cliente HTTP único. Un 401 con sesión la borra y lleva al login; sin sesión (login fallido) solo falla. */
export async function pedir<T>(ruta: string, { metodo, cuerpo, csv }: Opciones = {}): Promise<T> {
  if (!RUTA_API.test(ruta)) throw new Error("ruta_invalida"); // un dato de la URL nunca elige el host
  const token = await tokenActual();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (cuerpo !== undefined) headers["Content-Type"] = "application/json";
  if (csv) headers["Content-Type"] = "text/csv";

  const respuesta = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${ruta}`, {
    method: metodo,
    headers,
    body: csv ?? (cuerpo === undefined ? undefined : JSON.stringify(cuerpo)),
  });

  if (respuesta.status === 401 && token) {
    await cerrarSesion();
    window.location.assign("/login");
  }
  if (!respuesta.ok) throw new ErrorApi(respuesta.status);
  return respuesta.status === 204 ? (undefined as T) : ((await respuesta.json()) as T);
}

/** Igual que `pedir`, pero devuelve el cuerpo como archivo (un CSV para bajar). */
export async function descargar(ruta: string): Promise<Blob> {
  if (!RUTA_API.test(ruta)) throw new Error("ruta_invalida");
  const token = await tokenActual();
  const respuesta = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${ruta}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!respuesta.ok) throw new ErrorApi(respuesta.status);
  return respuesta.blob();
}
