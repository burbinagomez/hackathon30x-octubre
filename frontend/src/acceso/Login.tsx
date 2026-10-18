import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { pedir } from "../api/cliente";
import { cerrarSesion, guardarIdiomas, type RespuestaUsuario } from "../api/sesion";
import { supabase } from "../api/supabase";
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
      const { data, error } = await supabase.auth.signInWithPassword({ email, password: clave });
      if (error) {
        setFallo(error.code === "invalid_credentials" ? "error_credenciales" : "error_generico");
        return;
      }
      if (!data.session) throw new Error("sin sesión");
      guardarIdiomas(await pedir<RespuestaUsuario>("/usuarios/me"));
    } catch {
      // Autenticado en Supabase sin acceso a la API (403): no dejar una sesión a medias.
      await cerrarSesion();
      setFallo("error_generico");
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
