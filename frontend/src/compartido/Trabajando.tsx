import { useEffect, useId, useState, type ReactNode } from "react";

type Props = {
  /** Qué está pasando, en una línea ("Buscando en 2 fuentes"). Es también el nombre accesible del estado. */
  texto: string;
  /** Detalle opcional, uno por línea, cada uno con su anillo (por ejemplo, las fuentes que se consultan). */
  pasos?: string[];
  /** Qué está haciendo, en detalle: se ve al desplegar la píldora (como el "Thinking…" de Dapti). */
  detalle?: ReactNode;
};

const FLECHA_ABAJO = "▾"; // glifos, no texto: aria-hidden
const FLECHA_ARRIBA = "▴";
const reloj = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** Píldora de "estoy trabajando": anillo lima, texto y cronómetro. Las esperas largas (Overpass, la IA) se ven vivas. */
export default function Trabajando({ texto, pasos, detalle }: Props) {
  const [segundos, setSegundos] = useState(0);
  const [abierto, setAbierto] = useState(false);
  const id = useId();

  useEffect(() => {
    const intervalo = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(intervalo);
  }, []);

  const cabecera = (
    <>
      <span className="anillo" aria-hidden="true" />
      <span id={id} className="trabajando-texto">{texto}</span>
      <span className="trabajando-reloj" aria-hidden="true">{reloj(segundos)}</span>
      {detalle && <span className="trabajando-flecha" aria-hidden="true">{abierto ? FLECHA_ARRIBA : FLECHA_ABAJO}</span>}
    </>
  );

  return (
    <div role="status" aria-live="polite" aria-labelledby={id} className="trabajando">
      {detalle ? (
        <button type="button" className="trabajando-cabecera trabajando-alternar" aria-expanded={abierto}
          aria-labelledby={id} onClick={() => setAbierto((a) => !a)}>
          {cabecera}
        </button>
      ) : (
        <div className="trabajando-cabecera">{cabecera}</div>
      )}
      {detalle && abierto && <div className="trabajando-detalle">{detalle}</div>}
      {pasos && pasos.length > 0 && (
        <ul className="trabajando-pasos">
          {pasos.map((p) => (
            <li key={p}><span className="anillo anillo-chico" aria-hidden="true" />{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
