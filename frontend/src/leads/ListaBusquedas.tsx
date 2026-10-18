import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Enlace from "../compartido/Enlace";
import Esqueleto from "../compartido/Esqueleto";
import { entero } from "../compartido/formato";
import { listarBusquedas } from "./api";
import type { Busqueda } from "./tipos";

export default function ListaBusquedas() {
  const { t, i18n } = useTranslation();
  const [busquedas, setBusquedas] = useState<Busqueda[] | null>(null);
  const [fallo, setFallo] = useState(false);

  useEffect(() => {
    listarBusquedas().then((r) => setBusquedas(r.items)).catch(() => setFallo(true));
  }, []);

  const fecha = (iso: string) => new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" }).format(new Date(iso));
  const lugar = (b: Busqueda) =>
    b.ciudad ?? (b.departamento ? t("leads.departamento", { codigo: b.departamento }) : t("leads.todo_el_pais"));

  return (
    <main className="pantalla pantalla-ancha">
      <h1>{t("leads.titulo_busquedas")}</h1>
      {fallo && <p role="alert" className="error">{t("leads.error_busquedas")}</p>}
      {!fallo && busquedas === null && <Esqueleto />}
      {busquedas?.length === 0 && <p>{t("leads.sin_busquedas")}</p>}
      {busquedas && busquedas.length > 0 && (
        <ul className="lista-busquedas">
          {busquedas.map((b) => (
            <li key={b.id}>
              <Enlace a={`/busquedas/${b.id}/leads`}>
                {t("leads.resumen_busqueda", {
                  pais: t(`paises.${b.pais}`, { defaultValue: b.pais }),
                  lugar: lugar(b),
                  fecha: fecha(b.creada_en),
                  estado: t(`leads.estado.${b.estado}`, { defaultValue: b.estado }),
                  total: entero(b.total_leads),
                })}
              </Enlace>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
