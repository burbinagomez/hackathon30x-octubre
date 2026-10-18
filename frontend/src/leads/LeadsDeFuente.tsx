import { useTranslation } from "react-i18next";
import { listarLeadsDeFuente } from "./api";
import ListaLeads from "./ListaLeads";

/** `fuente` null = todos los leads del tenant. */
export default function LeadsDeFuente({ fuente }: { fuente: string | null }) {
  const { t } = useTranslation();
  const titulo = fuente
    ? t("leads.titulo_de_fuente", { fuente: t(`fuentes.${fuente}`, { defaultValue: fuente }) })
    : t("leads.titulo_todos");
  return <ListaLeads clave={`fuente:${fuente ?? ""}`} titulo={titulo} cargar={(p, c, i) => listarLeadsDeFuente(fuente, p, c, i)} />;
}
