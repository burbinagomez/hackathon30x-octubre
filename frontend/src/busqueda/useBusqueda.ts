import { useCallback, useState } from "react";
import { ejecutar, vistaPrevia } from "./api";
import type { PedidoVistaPrevia, ResultadoEjecucion, VistaPrevia } from "./tipos";

export type Ocupado = "vista" | "buscar" | null;

/** Vista previa -> Buscar -> resultado por fuente. Lo comparten Filtros y el chat de "En una frase". */
export function useBusqueda() {
  const [vista, setVista] = useState<VistaPrevia | null>(null);
  const [resultado, setResultado] = useState<ResultadoEjecucion | null>(null);
  const [ocupado, setOcupado] = useState<Ocupado>(null);
  const [fallo, setFallo] = useState(false);

  async function intentar(accion: () => Promise<void>, enCurso: Ocupado) {
    setFallo(false);
    setOcupado(enCurso);
    try {
      await accion();
    } catch {
      setFallo(true);
    } finally {
      setOcupado(null);
    }
  }

  // Estable: quien lo usa en un efecto no debe dispararlo en cada render.
  const reiniciar = useCallback(() => {
    setVista(null);
    setResultado(null);
  }, []);

  return {
    vista,
    resultado,
    ocupado,
    fallo,
    previsualizar: (pedido: PedidoVistaPrevia) => intentar(async () => setVista(await vistaPrevia(pedido)), "vista"),
    // Se queda en la pantalla: primero se lee qué pasó con cada fuente; el tablero es un clic aparte.
    buscar: () => intentar(async () => setResultado(await ejecutar(vista!.busqueda_id)), "buscar"),
    /** Cualquier cambio de criterios invalida la vista previa: el borrador congeló otros. */
    reiniciar,
    /** Solo suelta la vista previa (la sugerencia de una puerta no borra un resultado ya leído). */
    soltarVista: () => setVista(null),
  };
}
export type Busqueda = ReturnType<typeof useBusqueda>;
