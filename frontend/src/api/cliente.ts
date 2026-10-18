// Esqueleto (T034): hace la llamada sin tocar el token.
export type Opciones = { metodo?: string; cuerpo?: unknown };

export async function pedir<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  const respuesta = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${ruta}`, {
    method: opciones.metodo,
    body: opciones.cuerpo === undefined ? undefined : JSON.stringify(opciones.cuerpo),
  });
  return (await respuesta.json()) as T;
}
