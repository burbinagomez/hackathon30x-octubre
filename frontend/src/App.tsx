import { useEffect, useState, type ComponentType, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import Login from "./acceso/Login";
import { configuracionValida } from "./api/supabase";
import NuevaBusqueda from "./busqueda/NuevaBusqueda";
import LeadsDeBusqueda from "./leads/LeadsDeBusqueda";
import LeadsDeFuente from "./leads/LeadsDeFuente";
import ListaBusquedas from "./leads/ListaBusquedas";
import { aplicarIdioma } from "./compartido/idioma";
import SelectorIdioma from "./compartido/SelectorIdioma";
import Tablero from "./tablero/Tablero";

type Estado = { api: "…" | "ok" | "error"; db: "…" | "ok" | "error" };

const RUTAS: Record<string, ComponentType> = {
  "/login": Login,
  "/busqueda/nueva": NuevaBusqueda,
  "/tablero": Tablero,
  "/busquedas": ListaBusquedas,
};

// Solo un uuid: lo que no lo es no es una ruta (el id acaba en la URL de la API).
const LEADS_DE_BUSQUEDA = /^\/busquedas\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/leads$/;

function resolver(url: string): ReactElement | null {
  const [ruta, consulta = ""] = url.split("?");
  if (ruta === "/leads") {
    const fuente = new URLSearchParams(consulta).get("fuente");
    return <LeadsDeFuente key={fuente ?? ""} fuente={fuente} />;
  }
  const Pantalla = RUTAS[ruta];
  if (Pantalla) return <Pantalla />;
  const id = LEADS_DE_BUSQUEDA.exec(ruta)?.[1];
  return id ? <LeadsDeBusqueda key={id} id={id} /> : null;
}

function Salud() {
  const { t } = useTranslation();
  // Arranca sin "ok": si no, el e2e pasa antes de que /health conteste.
  const [estado, setEstado] = useState<Estado>({ api: "…", db: "…" });

  useEffect(() => {
    const url = `${import.meta.env.VITE_API_URL ?? ""}/health`;
    fetch(url)
      .then((r) => r.json())
      .then((body) => setEstado({ api: "ok", db: body.db === "ok" ? "ok" : "error" }))
      .catch(() => setEstado({ api: "error", db: "error" }));
  }, []);

  return <div className="salud">{t("salud.estado", { api: estado.api, db: estado.db })}</div>;
}

/** Raíz de composición: el router mínimo (por pathname y popstate) y el idioma de arranque. */
export default function App() {
  const { t } = useTranslation();
  const [ruta, setRuta] = useState(location.pathname + location.search);
  // Antes del primer render: la elección guardada tiene que ganar sin un parpadeo en otro idioma.
  useState(aplicarIdioma);

  useEffect(() => {
    const alNavegar = () => setRuta(location.pathname + location.search);
    window.addEventListener("popstate", alNavegar);
    return () => window.removeEventListener("popstate", alNavegar);
  }, []);

  if (!configuracionValida) return <main className="pantalla pantalla-tarjeta aviso" role="alert">{t("config.incompleta")}</main>;
  const pantalla = resolver(ruta);
  if (!pantalla) return <Salud />;
  return (
    <>
      {/* Login lleva su propio selector. */}
      {!ruta.startsWith("/login") && (
        <div className="barra">
          <SelectorIdioma />
        </div>
      )}
      {pantalla}
    </>
  );
}
