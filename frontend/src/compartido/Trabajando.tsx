import { useEffect, useId, useState } from "react";

type Props = {
  /** Qué está pasando, en una línea ("Buscando en 2 fuentes"). Es también el nombre accesible del estado. */
  texto: string;
  /** Detalle opcional, uno por línea, cada uno con su anillo (por ejemplo, las fuentes que se consultan). */
  pasos?: string[];
};

const reloj = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** Píldora de "estoy trabajando": anillo lima, texto y cronómetro. Las esperas largas (Overpass, la IA) se ven vivas. */
export default function Trabajando({ texto, pasos }: Props) {
  const [segundos, setSegundos] = useState(0);
  const id = useId();

  useEffect(() => {
    const intervalo = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(intervalo);
  }, []);

  return (
    <div role="status" aria-live="polite" aria-labelledby={id} className="trabajando">
      <div className="trabajando-cabecera">
        <span className="anillo" aria-hidden="true" />
        <span id={id} className="trabajando-texto">{texto}</span>
        <span className="trabajando-reloj" aria-hidden="true">{reloj(segundos)}</span>
      </div>
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
