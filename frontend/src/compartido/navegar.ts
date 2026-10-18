/** Cambia de pantalla sin recargar: App escucha popstate. */
export function navegar(ruta: string): void {
  history.pushState(null, "", ruta);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
