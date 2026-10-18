import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { tokenActual } from "../api/sesion";
import { navegar } from "../compartido/navegar";
import SelectorIdioma from "../compartido/SelectorIdioma";

/** Enlace con aspecto de botón: href real y navegación sin recargar al hacer clic normal. */
function Boton({ a, primario, children }: { a: string; primario?: boolean; children: string }) {
  return (
    <a
      href={a}
      className={`boton landing-boton${primario ? " boton-primario" : " landing-boton-secundario"}`}
      onClick={(e) => {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        navegar(a);
      }}
    >
      {children}
    </a>
  );
}

const CIFRAS = ["c1", "c2", "c3"] as const;
const PASOS = ["p1", "p2", "p3"] as const;
const PUNTOS = ["d1", "d2", "d3"] as const;

/** Home público (`/`): se ve con o sin sesión; solo cambia a dónde llevan los botones. */
export default function Landing() {
  const { t } = useTranslation();
  const [conSesion, setConSesion] = useState(false);

  useEffect(() => {
    let vivo = true;
    tokenActual().then((token) => vivo && setConSesion(Boolean(token)), () => undefined);
    return () => {
      vivo = false;
    };
  }, []);

  const empezar = conSesion ? "/busqueda/nueva" : "/login";
  const tablero = conSesion ? "/tablero" : "/login";

  return (
    <div className="landing">
      <div className="landing-contenedor">
        <div className="landing-barra">
          <SelectorIdioma />
        </div>
        <main>
          <section className="landing-hero" aria-labelledby="landing-titulo">
            <p className="landing-etiqueta">{t("landing.etiqueta")}</p>
            <h1 id="landing-titulo" className="landing-titulo">{t("landing.titulo")}</h1>
            <p className="landing-bajada">{t("landing.bajada")}</p>
            <div className="landing-acciones">
              <Boton a={empezar} primario>{t("landing.empezar")}</Boton>
              <Boton a={tablero}>{t("landing.ver_tablero")}</Boton>
            </div>
          </section>

          <section className="landing-seccion" aria-labelledby="landing-problema">
            <h2 id="landing-problema">{t("landing.problema.titulo")}</h2>
            <ul className="landing-rejilla">
              {CIFRAS.map((c) => (
                <li key={c} className="landing-tarjeta">
                  <p className="landing-cifra">{t(`landing.problema.${c}.cifra`)}</p>
                  <p>{t(`landing.problema.${c}.texto`)}</p>
                </li>
              ))}
            </ul>
          </section>

          <section className="landing-seccion" aria-labelledby="landing-solucion">
            <h2 id="landing-solucion">{t("landing.solucion.titulo")}</h2>
            <ol className="landing-pasos">
              {PASOS.map((p) => (
                <li key={p} className="landing-paso">
                  <div className="landing-tarjeta">
                    <h3>{t(`landing.solucion.${p}.titulo`)}</h3>
                    <p>{t(`landing.solucion.${p}.texto`)}</p>
                  </div>
                  <span className="landing-flecha" aria-hidden="true" />
                </li>
              ))}
            </ol>
          </section>

          <section className="landing-seccion" aria-labelledby="landing-diferencial">
            <h2 id="landing-diferencial">{t("landing.diferencial.titulo")}</h2>
            <ul className="landing-puntos">
              {PUNTOS.map((d) => (
                <li key={d}>{t(`landing.diferencial.${d}`)}</li>
              ))}
            </ul>
          </section>

          <section className="landing-final" aria-labelledby="landing-cta">
            <h2 id="landing-cta" className="landing-titulo-cta">{t("landing.cta")}</h2>
            <div className="landing-acciones">
              <Boton a={empezar} primario>{t("landing.empezar")}</Boton>
            </div>
          </section>
        </main>
        <footer className="landing-pie">{t("landing.viabilidad")}</footer>
      </div>
    </div>
  );
}
