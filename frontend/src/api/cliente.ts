// Esqueleto (T034): hace la llamada sin tocar el token.
export async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const respuesta = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${ruta}`, init);
  return (await respuesta.json()) as T;
}
