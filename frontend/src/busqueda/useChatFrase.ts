import { useState } from "react";
import { ErrorApi } from "../api/cliente";
import { sugerirDesdeFrase, type Sugerencia, type Turno } from "./api";
import { TOPE_POR_DEFECTO } from "./formulario";

export const MAX_MENSAJE = 500;
/** El back acepta hasta 12 turnos de historial: con 12 en pantalla la conversación se cierra y se empieza de nuevo. */
export const MAX_TURNOS = 12;

export type AvisoChat = "error_no_disponible" | "error_interpretacion";

/** La conversación de "En una frase". Vive arriba de la pestaña para que no se pierda al pasar por Filtros. */
export function useChatFrase() {
  const [mensajes, setMensajes] = useState<Turno[]>([]);
  const [texto, setTexto] = useState("");
  const [sugerencia, setSugerencia] = useState<Sugerencia | null>(null);
  const [pensando, setPensando] = useState(false);
  const [ciiuDescartado, setCiiuDescartado] = useState(false);
  const [aviso, setAviso] = useState<AvisoChat | null>(null);
  const [tope, setTope] = useState(TOPE_POR_DEFECTO);

  const limite = mensajes.length >= MAX_TURNOS;

  async function enviar() {
    const frase = texto.trim();
    if (!frase || pensando || limite) return;
    const previos = mensajes;
    const historial = previos.map((m) => ({ rol: m.rol, texto: m.texto.slice(0, MAX_MENSAJE) }));
    // El mensaje aparece al enviar; si la IA falla se retira y vuelve al cuadro, para no perder lo escrito.
    setMensajes([...previos, { rol: "usuario", texto: frase }]);
    setTexto("");
    setAviso(null);
    setPensando(true);
    try {
      const r = await sugerirDesdeFrase(frase, historial);
      const respuesta = r.pregunta ?? r.explicacion;
      setMensajes((m) => (respuesta ? [...m, { rol: "asistente", texto: respuesta }] : m));
      setSugerencia(r.pregunta ? null : r.sugerencia);
      setCiiuDescartado(!r.pregunta && r.ciiu_descartado === true);
    } catch (e) {
      setMensajes(previos);
      setTexto(frase);
      setAviso(e instanceof ErrorApi && e.estado === 503 ? "error_no_disponible" : "error_interpretacion");
    } finally {
      setPensando(false);
    }
  }

  function empezarDeNuevo() {
    setMensajes([]);
    setTexto("");
    setSugerencia(null);
    setCiiuDescartado(false);
    setAviso(null);
    setTope(TOPE_POR_DEFECTO);
  }

  return {
    mensajes, texto, setTexto, sugerencia, ciiuDescartado, pensando, aviso, limite, tope, setTope,
    topeEditado: tope !== TOPE_POR_DEFECTO,
    enviar, empezarDeNuevo,
  };
}
export type Chat = ReturnType<typeof useChatFrase>;
