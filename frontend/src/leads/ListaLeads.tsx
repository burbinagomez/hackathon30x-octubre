import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ErrorApi } from "../api/cliente";
import Enlace from "../compartido/Enlace";
import { RUTA_BUSQUEDAS } from "../compartido/rutas";
import Atribuciones from "../compartido/Atribuciones";
import { entero } from "../compartido/formato";
import type { PaginaLeads } from "./tipos";

type Campo = "nombre" | "tipo" | "fuentes" | "ciudad" | "web" | "telefono" | "email" | "licencia";

/** Lista paginada de leads: la misma para una búsqueda y para una fuente. `clave` cambia cuando cambia lo que se lista. */
export default function ListaLeads({ clave, titulo, cargar }: {
  clave: string;
  titulo: string;
  cargar: (pagina: number) => Promise<PaginaLeads>;
}) {
  const { t } = useTranslation();
  const [pagina, setPagina] = useState(1);
  const [datos, setDatos] = useState<PaginaLeads | null>(null);
  const [fallo, setFallo] = useState<"no_encontrada" | "error_leads" | null>(null);

  useEffect(() => {
    setFallo(null);
    cargar(pagina)
      .then(setDatos)
      .catch((e) => setFallo(e instanceof ErrorApi && e.estado === 404 ? "no_encontrada" : "error_leads"));
    // `cargar` es nuevo en cada render: lo que dispara la recarga es la clave y la página.
  }, [clave, pagina]);

  const cabecera = (
    <>
      <Enlace a={RUTA_BUSQUEDAS}>{t("leads.volver")}</Enlace>
      <h1>{titulo}</h1>
      {fallo && <p role="alert" className="error">{t(`leads.${fallo}`)}</p>}
    </>
  );
  if (!datos) return <main className="pantalla pantalla-ancha">{cabecera}</main>;

  const paginas = Math.max(1, Math.ceil(datos.total / datos.tamano));
  const sino = (v: boolean | null) => (v === null ? "" : v ? t("leads.si") : t("leads.no"));
  // Teléfono y correo: la API manda null mientras no haya dato; esa columna no se pinta (nunca un valor de contacto).
  const hay = (c: "tiene_telefono" | "tiene_email") => datos.items.some((i) => i[c] !== null);
  const campos: Campo[] = ["nombre", "tipo", "fuentes", "ciudad", "web"];
  if (hay("tiene_telefono")) campos.push("telefono");
  if (hay("tiene_email")) campos.push("email");
  campos.push("licencia");

  return (
    <main className="pantalla pantalla-ancha">
      {cabecera}
      {datos.items.length === 0 && <p>{t("leads.sin_leads")}</p>}
      {datos.items.length > 0 && (
        <>
          <p className="nota">{t("leads.total", { total: entero(datos.total) })}</p>
          <div className="tabla-scroll">
            <table className="tabla-leads">
              <thead>
                <tr>{campos.map((c) => <th key={c}>{t(`leads.${c}`)}</th>)}</tr>
              </thead>
              <tbody>
                {datos.items.map((l) => {
                  const celdas: Record<Campo, string> = {
                    // Persona natural: la API no manda nombre; el texto protegido es el único que se muestra.
                    nombre: l.tipo_titular === "juridica" && l.nombre ? l.nombre : t("leads.natural_protegida"),
                    tipo: t(`leads.tipo_titular.${l.tipo_titular}`),
                    fuentes: l.fuentes.map((f) => t(`fuentes.${f}`, { defaultValue: f })).join(", "),
                    ciudad: l.ciudad ?? "",
                    web: sino(l.tiene_web),
                    telefono: sino(l.tiene_telefono),
                    email: sino(l.tiene_email),
                    licencia: [...new Set(l.licencias)].join(", "),
                  };
                  return (
                    <tr key={l.id}>
                      {campos.map((c) => <td key={c} data-etiqueta={t(`leads.${c}`)}>{celdas[c]}</td>)}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <nav className="paginacion" aria-label={titulo}>
            <button type="button" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>{t("leads.anterior")}</button>
            <span>{t("leads.pagina_de", { pagina: datos.pagina, paginas })}</span>
            <button type="button" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>{t("leads.siguiente")}</button>
          </nav>
        </>
      )}
      <Atribuciones atribuciones={datos.atribuciones} />
    </main>
  );
}
