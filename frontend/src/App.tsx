import { useEffect, useState } from "react";

type Estado = { api: "ok" | "error"; db: "ok" | "error" };

export default function App() {
  const [estado, setEstado] = useState<Estado>({ api: "ok", db: "ok" });

  useEffect(() => {
    const url = `${import.meta.env.VITE_API_URL ?? ""}/health`;
    fetch(url)
      .then((r) => r.json())
      .then((body) => setEstado({ api: "ok", db: body.db === "ok" ? "ok" : "error" }))
      .catch(() => setEstado({ api: "error", db: "error" }));
  }, []);

  return (
    <div>
      API: {estado.api} · DB: {estado.db}
    </div>
  );
}
