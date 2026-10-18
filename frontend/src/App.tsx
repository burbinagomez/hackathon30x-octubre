import { useEffect, useState, type ComponentType } from "react";
import { useTranslation } from "react-i18next";
import Login from "./acceso/Login";
import { configuracionValida } from "./api/supabase";
import NuevaBusqueda from "./busqueda/NuevaBusqueda";
import { aplicarIdioma } from "./compartido/idioma";
import SelectorIdioma from "./compartido/SelectorIdioma";
import Tablero from "./tablero/Tablero";

type Estado = { api: "…" | "ok" | "error"; db: "…" | "ok" | "error" };

const RUTAS: Record<string, ComponentType> = {
  "/login": Login,
  "/busqueda/nueva": NuevaBusqueda,
  "/tablero": Tablero,
};

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

  return <div>{t("salud.estado", { api: estado.api, db: estado.db })}</div>;
}

/** Raíz de composición: el router mínimo (por pathname y popstate) y el idioma de arranque. */
export default function App() {
  const { t } = useTranslation();
  const [ruta, setRuta] = useState(location.pathname);
  // Antes del primer render: la elección guardada tiene que ganar sin un parpadeo en otro idioma.
  useState(aplicarIdioma);

  useEffect(() => {
    const alNavegar = () => setRuta(location.pathname);
    window.addEventListener("popstate", alNavegar);
    return () => window.removeEventListener("popstate", alNavegar);
  }, []);

  if (!configuracionValida) return <main role="alert">{t("config.incompleta")}</main>;
  const Pantalla = RUTAS[ruta];
  if (!Pantalla) return <Salud />;
  return (
    <>
      {/* Login lleva su propio selector. */}
      {ruta !== "/login" && <SelectorIdioma />}
      <Pantalla />
    </>
  );
}
