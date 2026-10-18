import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

type Estado = { api: "…" | "ok" | "error"; db: "…" | "ok" | "error" };

export default function App() {
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

  return (
    <div>{t("salud.estado", { api: estado.api, db: estado.db })}</div>
  );
}
