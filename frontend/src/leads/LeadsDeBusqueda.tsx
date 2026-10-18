import { useTranslation } from "react-i18next";
import { listarLeads } from "./api";
import ListaLeads from "./ListaLeads";

export default function LeadsDeBusqueda({ id }: { id: string }) {
  const { t } = useTranslation();
  return <ListaLeads clave={`busqueda:${id}`} titulo={t("leads.titulo_leads")} cargar={(p) => listarLeads(id, p)} />;
}
