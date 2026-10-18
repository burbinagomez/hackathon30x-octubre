import { useEffect, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { moneda } from "../compartido/formato";
import Trabajando from "../compartido/Trabajando";
import { divisionesDe, type Sugerencia } from "./api";
import BloqueBusqueda from "./BloqueBusqueda";
import { aPedido, conSugerencia, INICIAL } from "./formulario";
import type { Actividad, Division } from "./tipos";
import type { Busqueda } from "./useBusqueda";
import { MAX_MENSAJE, type Chat } from "./useChatFrase";

type Props = {
  chat: Chat;
  busqueda: Busqueda;
  actividades: Actividad[];
  alEditarEnFiltros: (sugerencia: Sugerencia) => void;
};

/** Qué voy a buscar, con nombres y no códigos (la sugerencia viaja con los códigos de la geografía y del catálogo). */
function ResumenSugerencia({ s, actividades, divisiones }: { s: Sugerencia; actividades: Actividad[]; divisiones: Division[] }) {
  const { t, i18n } = useTranslation();
  const en = i18n.language === "en";
  const actividad = actividades.find((a) => a.codigo === s.ciiu);
  const division = divisiones.find((d) => d.codigo_nativo === s.departamento);
  const ciudad = division?.municipios.find((m) => m.codigo_nativo === s.ciudad)?.nombre ?? s.ciudad;
  const filas: [string, string | null][] = [
    ["pais", t(`paises.${s.pais}`, { defaultValue: s.pais })],
    ["ciiu", s.ciiu && (actividad ? (en ? actividad.nombre_en ?? actividad.nombre_es : actividad.nombre_es) : s.ciiu)],
    ["departamento", s.departamento && (division ? (en ? division.nombre_en : division.nombre_es) : s.departamento)],
    ["ciudad", s.departamento ? ciudad : null],
    ["ingresos_min", s.ingresos_min === null ? null : moneda(s.ingresos_min)],
    ["palabras_clave", s.palabras_clave.length > 0 ? s.palabras_clave.join(", ") : null],
    ["exclusiones", s.exclusiones.length > 0 ? s.exclusiones.join(", ") : null],
  ];
  return (
    <dl className="resumen">
      {filas.map(([clave, valor]) =>
        valor ? (
          <div key={clave}>
            <dt>{t(`criterios.${clave}`)}</dt>
            <dd>{valor}</dd>
          </div>
        ) : clave === "ciiu" ? (
          <div key={clave}>
            <dt>{t("criterios.ciiu")}</dt>
            <dd className="resumen-aviso">{t("busqueda.frase.actividad_falta")}</dd>
          </div>
        ) : null,
      )}
    </dl>
  );
}

export default function ChatFrase({ chat, busqueda, actividades, alEditarEnFiltros }: Props) {
  const { t } = useTranslation();
  const { sugerencia } = chat;
  const [divisiones, setDivisiones] = useState<Division[]>([]);
  const pais = sugerencia?.pais;
  const reiniciarBusqueda = busqueda.reiniciar;

  useEffect(() => {
    if (!pais) return;
    let vigente = true;
    divisionesDe(pais).then((r) => vigente && setDivisiones(r.divisiones)).catch(() => undefined);
    return () => {
      vigente = false;
    };
  }, [pais]);

  // Una sugerencia nueva (o ninguna) deja sin vigencia la vista previa y el resultado de la anterior.
  useEffect(() => reiniciarBusqueda(), [sugerencia, reiniciarBusqueda]);

  function alTeclear(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void chat.enviar();
    }
  }

  const bloqueado = chat.pensando || chat.limite;
  const enCurso = chat.mensajes.length > 0;
  const pedido = sugerencia ? aPedido({ ...conSugerencia(INICIAL, sugerencia), tope: chat.tope }) : null;

  return (
    <div className="tarjeta panel-intake chat" role="tabpanel">
      <div role="log" aria-live="polite" aria-label={t("busqueda.frase.conversacion")} className="chat-mensajes">
        {chat.mensajes.length === 0 && !chat.aviso && <p className="ayuda">{t("busqueda.frase.ayuda")}</p>}
        {chat.mensajes.map((m, i) => (
          <div key={i} className={m.rol === "usuario" ? "burbuja burbuja-usuario" : "burbuja burbuja-ia"}>
            {m.rol === "asistente" && <span className="burbuja-nombre">{t("busqueda.frase.asistente")}</span>}
            <p>{m.texto}</p>
          </div>
        ))}
        {chat.aviso && <p role="alert" className="error">{t(`busqueda.frase.${chat.aviso}`)}</p>}
      </div>
      {chat.pensando && <Trabajando texto={t("busqueda.trabajando.frase")} />}
      {chat.limite && <p role="status" className="aviso-ancho">{t("busqueda.frase.limite_turnos")}</p>}

      <div className="chat-entrada">
        {/* Después de la primera respuesta la pregunta ya está contestada: queda solo para lectores de pantalla. */}
        <label htmlFor="frase" className={enCurso ? "solo-lector" : undefined}>{t("busqueda.frase.etiqueta")}</label>
        <textarea id="frase" maxLength={MAX_MENSAJE} value={chat.texto} disabled={chat.limite}
          rows={enCurso ? 1 : undefined} placeholder={enCurso ? t("busqueda.frase.ajustar") : undefined}
          className={enCurso ? "chat-entrada-corta" : undefined}
          onChange={(e) => chat.setTexto(e.target.value)} onKeyDown={alTeclear} />
        <div className="acciones acciones-fin">
          {chat.mensajes.length > 0 && (
            <button type="button" className="boton" disabled={chat.pensando} onClick={chat.empezarDeNuevo}>
              {t("busqueda.frase.empezar_de_nuevo")}
            </button>
          )}
          <button type="button" className="boton boton-primario" disabled={!chat.texto.trim() || bloqueado}
            aria-busy={chat.pensando} onClick={chat.enviar}>
            {chat.pensando && <span className="anillo anillo-chico" aria-hidden="true" />}
            {chat.pensando ? t("busqueda.frase.pensando") : t("busqueda.frase.enviar")}
          </button>
        </div>
      </div>

      {sugerencia && pedido && (
        <div className="chat-busqueda">
          <section className="tarjeta" aria-labelledby="voy-a-buscar">
            <h2 id="voy-a-buscar">{t("busqueda.frase.voy_a_buscar")}</h2>
            <ResumenSugerencia s={sugerencia} actividades={actividades} divisiones={divisiones} />
            {chat.ciiuDescartado && <p role="status" className="resumen-aviso">{t("busqueda.frase.ciiu_descartado")}</p>}
          </section>
          {!sugerencia.ciiu && <p className="aviso-ancho">{t("busqueda.frase.sin_actividad")}</p>}
          <div className="campo">
            <label htmlFor="tope-chat">{t("busqueda.tope")}</label>
            <input id="tope-chat" type="number" value={chat.tope} onChange={(e) => { chat.setTope(e.target.value); busqueda.reiniciar(); }} />
          </div>
          <BloqueBusqueda busqueda={busqueda} pedido={pedido} tope={Number(chat.tope)}
            puedeVista={Boolean(sugerencia.ciiu) && Number(chat.tope) > 0} buscarPrimario={Boolean(sugerencia.ciiu)}
            extra={
              <button type="button" className={sugerencia.ciiu ? "boton" : "boton boton-primario"}
                onClick={() => alEditarEnFiltros(sugerencia)}>
                {t("busqueda.frase.editar_en_filtros")}
              </button>
            } />
        </div>
      )}
    </div>
  );
}
