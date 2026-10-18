import { useState } from "react";
import { useTranslation } from "react-i18next";
import Trabajando from "../compartido/Trabajando";
import { enriquecer, listarLeads, type ResumenEnriquecimiento } from "./api";
import ListaLeads from "./ListaLeads";

export default function LeadsDeBusqueda({ id }: { id: string }) {
  const { t } = useTranslation();
  const [trabajando, setTrabajando] = useState(false);
  const [resumen, setResumen] = useState<ResumenEnriquecimiento | null>(null);
  const [fallo, setFallo] = useState(false);
  const [version, setVersion] = useState(0); // cambia al terminar una tanda: la lista se vuelve a pedir

  async function tanda() {
    setFallo(false);
    setTrabajando(true);
    try {
      setResumen(await enriquecer(id));
      setVersion((v) => v + 1);
    } catch {
      setFallo(true);
    } finally {
      setTrabajando(false);
    }
  }

  const etiqueta = resumen && resumen.pendientes > 0 ? t("enriquecer.seguir") : t("enriquecer.boton");
  return (
    <>
      <section className="tarjeta panel-enriquecer">
        <p className="ayuda">{t("enriquecer.ayuda")}</p>
        <div className="acciones acciones-fin">
          {(!resumen || resumen.pendientes > 0) && (
            <button type="button" className="boton boton-primario" disabled={trabajando} aria-busy={trabajando} onClick={tanda}>
              {trabajando && <span className="anillo anillo-chico" aria-hidden="true" />}
              {etiqueta}
            </button>
          )}
        </div>
        {trabajando && <Trabajando texto={t("enriquecer.trabajando")} flotante />}
        {resumen && !trabajando && (
          <p role="status" className="aviso aviso-ancho">
            {t("enriquecer.resumen", { procesados: resumen.procesados, contactables: resumen.contactables, pendientes: resumen.pendientes })}
          </p>
        )}
        {fallo && <p role="alert" className="error">{t("enriquecer.error")}</p>}
      </section>
      <ListaLeads key={version} clave={`busqueda:${id}:${version}`} titulo={t("leads.titulo_leads")} cargar={(p, c) => listarLeads(id, p, c)} />
    </>
  );
}
