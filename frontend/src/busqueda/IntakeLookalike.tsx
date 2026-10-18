import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ErrorApi } from "../api/cliente";
import { lookalike, type RespuestaLookalike, type SugerenciaIntake } from "./apiLookalike";
import { EMPRESAS_DE_EJEMPLO } from "./ejemploLookalike";

const MINIMO = 5;
const MAXIMO = 50;

type Props = {
  /** Recibe la sugerencia para prellenar el formulario; la pantalla que lo monta decide qué pestaña muestra. */
  alSugerir: (sugerencia: SugerenciaIntake) => void;
};

const MENSAJE_DE_ERROR: Record<number, "no_disponible" | "rango"> = { 503: "no_disponible", 422: "rango" };

export default function IntakeLookalike({ alSugerir }: Props) {
  const { t } = useTranslation();
  const [texto, setTexto] = useState("");
  const [respuesta, setRespuesta] = useState<RespuestaLookalike | null>(null);
  const [error, setError] = useState<"no_disponible" | "rango" | "error" | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function sugerir() {
    const nombres = texto.split("\n").map((n) => n.trim()).filter(Boolean);
    setRespuesta(null);
    if (nombres.length < MINIMO || nombres.length > MAXIMO) {
      setError("rango");
      return;
    }
    setError(null);
    setEnviando(true);
    try {
      const r = await lookalike(nombres);
      setRespuesta(r);
      alSugerir(r.sugerencia);
    } catch (e) {
      setError(e instanceof ErrorApi ? (MENSAJE_DE_ERROR[e.estado] ?? "error") : "error");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="formulario formulario-ancho">
      <h2>{t("intake.lookalike.titulo")}</h2>
      <p>{t("intake.lookalike.ayuda")}</p>
      <div className="campo">
        <label htmlFor="lookalike-nombres">{t("intake.lookalike.nombres")}</label>
        <textarea id="lookalike-nombres" rows={8} value={texto} onChange={(e) => setTexto(e.target.value)} />
      </div>
      <div className="acciones">
        <button type="button" className="boton" onClick={() => setTexto(EMPRESAS_DE_EJEMPLO.join("\n"))}>
          {t("intake.lookalike.ejemplo")}
        </button>
        <button type="button" className="boton boton-primario" disabled={enviando} onClick={sugerir}>
          {enviando ? t("intake.lookalike.enviando") : t("intake.lookalike.sugerir")}
        </button>
      </div>
      {error && <p role="alert" className="error">{t(`intake.lookalike.${error}`)}</p>}
      {respuesta && (
        <div>
          <p>{t("intake.lookalike.resueltos", { n: respuesta.resueltos })}</p>
          <h3>{t("intake.lookalike.explicacion")}</h3>
          <h4>{t("intake.lookalike.ciiu")}</h4>
          <ul>
            {respuesta.explicacion.ciiu.map(([codigo, n]) => <li key={codigo}>{`${codigo}: ${n}`}</li>)}
          </ul>
          <h4>{t("intake.lookalike.departamento")}</h4>
          <ul>
            {respuesta.explicacion.departamento.map(([codigo, n]) => <li key={codigo}>{`${codigo}: ${n}`}</li>)}
          </ul>
          {respuesta.no_resueltos.length > 0 && (
            <>
              <h3>{t("intake.lookalike.no_resueltos")}</h3>
              <ul>
                {respuesta.no_resueltos.map((nombre) => <li key={nombre}>{nombre}</li>)}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
