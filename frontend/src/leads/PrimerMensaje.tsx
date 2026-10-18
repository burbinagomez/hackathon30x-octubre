import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ErrorApi } from "../api/cliente";
import { contactosDe, enviarMensajes, marcarRespondio, tasaRespuesta, vistaEnvio,
  type ContactoEnvio, type TasaCanal, type VistaEnvio } from "./api";

/** Primer mensaje por email a los contactables de la búsqueda y registro de la respuesta (007). */
export default function PrimerMensaje({ id }: { id: string }) {
  const { t } = useTranslation();
  const [vista, setVista] = useState<VistaEnvio | null>(null);
  const [contactos, setContactos] = useState<ContactoEnvio[]>([]);
  const [tasa, setTasa] = useState<TasaCanal[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviados, setEnviados] = useState<number | null>(null);

  const recargar = () => {
    contactosDe(id).then((r) => setContactos(r.items)).catch(() => undefined);
    tasaRespuesta().then((r) => setTasa(r.items)).catch(() => undefined);
  };
  useEffect(recargar, [id]);

  async function intentar(accion: () => Promise<void>) {
    setAviso(null);
    setOcupado(true);
    try {
      await accion();
    } catch (e) {
      const codigo = e instanceof ErrorApi ? e.estado : 0;
      setAviso(codigo === 503 ? "no_configurado" : codigo === 409 ? "primero_vista" : "error");
    } finally {
      setOcupado(false);
      recargar();
    }
  }

  return (
    <section className="pantalla pantalla-ancha primer-mensaje" aria-labelledby="primer-mensaje">
      <div className="tarjeta">
        <h2 id="primer-mensaje">{t("envio.titulo")}</h2>
        <p className="ayuda">{t("envio.ayuda")}</p>
        <div className="acciones acciones-fin">
          <button type="button" className="boton" disabled={ocupado} onClick={() => intentar(async () => setVista(await vistaEnvio(id)))}>
            {t("envio.ver")}
          </button>
          <button type="button" className="boton boton-primario" disabled={ocupado || !vista || vista.a_enviar === 0}
            onClick={() => intentar(async () => { const r = await enviarMensajes(id); setAviso(null); setVista(null); setEnviados(r.enviados); })}>
            {t("envio.enviar")}
          </button>
        </div>
        {vista && (
          <div className="vista-envio">
            <p role="status">{t("envio.resumen", { a_enviar: vista.a_enviar, modo: vista.modo })}</p>
            {vista.asunto && <p><strong>{vista.asunto}</strong></p>}
            {vista.cuerpo && <pre className="cuerpo-envio">{vista.cuerpo}</pre>}
          </div>
        )}
        {enviados !== null && <p role="status">{t("envio.enviados", { count: enviados })}</p>}
        {aviso && <p role="alert" className="error">{t(`envio.${aviso}`)}</p>}
        {contactos.length > 0 && (
          <ul className="lista-envios">
            {contactos.map((c, n) => (
              <li key={c.id}>
                <span>{t("envio.contacto", { n: n + 1 })} · {t(`envio.estado.${c.estado}`, { defaultValue: c.estado })}</span>
                {c.respondio_en ? <span>{t("envio.respondio")}</span> : c.enviado_en && (
                  <button type="button" className="boton boton-chico" disabled={ocupado}
                    onClick={() => intentar(async () => { await marcarRespondio(c.id); })}>
                    {t("envio.marcar_respondio")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {tasa.map((f) => (
          <p key={f.canal} className="tasa-respuesta">
            {t("envio.tasa", { contactados: f.contactados, respondieron: f.respondieron,
              tasa: f.tasa === null ? "—" : `${Math.round(Number(f.tasa) * 100)} %` })}
          </p>
        ))}
      </div>
    </section>
  );
}
