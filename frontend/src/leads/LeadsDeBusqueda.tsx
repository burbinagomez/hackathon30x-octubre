import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { estadoEnriquecimiento, iniciarEnriquecimiento, listarLeads, type EstadoEnriquecimiento } from "./api";
import ListaLeads from "./ListaLeads";
import PrimerMensaje from "./PrimerMensaje";

const CADA_MS = 4000;

/** Lista de leads de una búsqueda. La búsqueda de contactos corre sola en el servidor: acá solo se muestra el avance. */
export default function LeadsDeBusqueda({ id, cadaMs = CADA_MS }: { id: string; cadaMs?: number }) {
  const { t } = useTranslation();
  const [estado, setEstado] = useState<EstadoEnriquecimiento | null>(null);
  const [fallo, setFallo] = useState(false);
  const [version, setVersion] = useState(0); // cambia con `procesados`: la lista se vuelve a pedir
  const ultimo = useRef<number | null>(null);

  function arrancar() {
    setFallo(false);
    iniciarEnriquecimiento(id).then(setEstado).catch(() => setFallo(true)); // idempotente: si ya corre, devuelve su estado
  }

  useEffect(arrancar, [id]);

  useEffect(() => {
    if (!estado?.en_curso) return;
    const h = setTimeout(() => {
      estadoEnriquecimiento(id).then(setEstado).catch(() => setFallo(true));
    }, cadaMs);
    return () => clearTimeout(h);
  }, [estado, id, cadaMs]);

  useEffect(() => {
    if (!estado) return;
    if (ultimo.current !== null && ultimo.current !== estado.procesados) setVersion((v) => v + 1);
    ultimo.current = estado.procesados;
  }, [estado?.procesados]);

  const hayError = fallo || !!estado?.error;
  const progreso = (hayError || estado) && (
    <span className="estado-contactos" role="status">
      {hayError ? (
        <>
          <span>{t("enriquecer.error")}</span>
          <button type="button" className="enlace-reintentar" onClick={arrancar}>{t("enriquecer.reintentar")}</button>
        </>
      ) : estado?.en_curso ? (
        <>
          <span className="anillo anillo-chico" aria-hidden="true" />
          <span>{t("enriquecer.buscando", { procesados: estado.procesados, total: estado.total })}</span>
        </>
      ) : estado && estado.total > 0 ? (
        <span>{t("enriquecer.listo", { contactables: estado.contactables })}</span>
      ) : null}
    </span>
  );

  return (
    <>
      <ListaLeads clave={`busqueda:${id}:${version}`} titulo={t("leads.titulo_leads")} cargar={(p, c, i) => listarLeads(id, p, c, i)}
        progreso={progreso || undefined} />
      <PrimerMensaje id={id} />
    </>
  );
}
