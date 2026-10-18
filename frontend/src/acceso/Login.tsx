import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ErrorApi, pedir } from "../api/cliente";
import { guardarSesion, type RespuestaSesion } from "../api/sesion";
import { aplicarIdioma } from "../compartido/idioma";
import { navegar } from "../compartido/navegar";
import SelectorIdioma from "../compartido/SelectorIdioma";

export default function Login() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [clave, setClave] = useState("");
  const [fallo, setFallo] = useState<"error_credenciales" | "error_generico" | null>(null);

  async function ingresar(e: FormEvent) {
    e.preventDefault();
    try {
      guardarSesion(await pedir<RespuestaSesion>("/auth/sesion", { metodo: "POST", cuerpo: { email, clave } }));
    } catch (e) {
      setFallo(e instanceof ErrorApi && e.estado === 401 ? "error_credenciales" : "error_generico");
      return;
    }
    aplicarIdioma();
    navegar("/busqueda/nueva");
  }

  return (
    <main>
      <SelectorIdioma />
      <h1>{t("acceso.titulo")}</h1>
      <form onSubmit={ingresar}>
        <label htmlFor="email">{t("acceso.email")}</label>
        <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="clave">{t("acceso.clave")}</label>
        <input id="clave" type="password" autoComplete="current-password" value={clave} onChange={(e) => setClave(e.target.value)} />
        {fallo && <p role="alert">{t(`acceso.${fallo}`)}</p>}
        <button type="submit">{t("acceso.ingresar")}</button>
      </form>
    </main>
  );
}
