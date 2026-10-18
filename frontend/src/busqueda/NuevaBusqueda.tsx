import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { navegar } from "../compartido/navegar";
import { ejecutar, listarActividades, vistaPrevia } from "./api";
import ResultadoVistaPrevia from "./ResultadoVistaPrevia";
import type { Actividad, PedidoVistaPrevia, VistaPrevia } from "./tipos";

const PAISES = ["CO", "MX", "BR", "PE"];
const CANALES = ["email"];

type Formulario = Record<
  "pais" | "ciiu" | "departamento" | "ingresosMin" | "palabrasClave" | "exclusiones" | "canal" | "tope" | "mensaje",
  string
>;
const INICIAL: Formulario = {
  pais: "CO", ciiu: "", departamento: "", ingresosMin: "", palabrasClave: "",
  exclusiones: "", canal: "email", tope: "", mensaje: "",
};

const lista = (texto: string) => texto.split(",").map((p) => p.trim()).filter(Boolean);

function aPedido(f: Formulario): PedidoVistaPrevia {
  return {
    pais: f.pais,
    ciiu: f.ciiu,
    departamento: f.departamento || undefined,
    ingresos_min: f.ingresosMin ? Number(f.ingresosMin) : undefined,
    palabras_clave: lista(f.palabrasClave),
    exclusiones: lista(f.exclusiones),
    canal_preferido: f.canal,
    tope_gasto_usd: Number(f.tope),
    mensaje_base: f.mensaje,
  };
}

function Campo({ id, etiqueta, children }: { id: string; etiqueta: string; children: ReactNode }) {
  return (
    <div className="campo">
      <label htmlFor={id}>{etiqueta}</label>
      {children}
    </div>
  );
}

export default function NuevaBusqueda() {
  const { t, i18n } = useTranslation();
  const [form, setForm] = useState<Formulario>(INICIAL);
  const [vista, setVista] = useState<VistaPrevia | null>(null);
  const [actividades, setActividades] = useState<Actividad[]>([]);
  const [fallo, setFallo] = useState(false);

  useEffect(() => {
    listarActividades().then(setActividades).catch(() => undefined);
  }, []);

  // Cualquier cambio invalida la vista previa: el borrador congeló otros criterios.
  function cambiar(campo: keyof Formulario, valor: string) {
    setForm((f) => ({ ...f, [campo]: valor }));
    setVista(null);
  }

  async function intentar(accion: () => Promise<void>) {
    setFallo(false);
    try {
      await accion();
    } catch {
      setFallo(true);
    }
  }

  const entrada = (campo: keyof Formulario, etiqueta: string, tipo = "text") => (
    <Campo id={campo} etiqueta={etiqueta}>
      <input id={campo} type={tipo} value={form[campo]} onChange={(e) => cambiar(campo, e.target.value)} />
    </Campo>
  );
  // Fuera del JSX: la regla de literales mira los argumentos de una llamada dentro de él.
  const departamento = entrada("departamento", t("busqueda.departamento"));
  const ingresosMin = entrada("ingresosMin", t("busqueda.ingresos_min"), "number");
  const palabrasClave = entrada("palabrasClave", t("busqueda.palabras_clave"));
  const exclusiones = entrada("exclusiones", t("busqueda.exclusiones"));
  const tope = entrada("tope", t("busqueda.tope"), "number");
  const nombre = (a: Actividad) => (i18n.language === "en" ? a.nombre_en ?? a.nombre_es : a.nombre_es);
  const puedeBuscar = vista !== null && vista.dentro_del_tope && vista.fuentes.length > 0;

  return (
    <main className="pantalla">
      <h1>{t("busqueda.titulo")}</h1>
      <div className="formulario formulario-ancho">
      <Campo id="pais" etiqueta={t("busqueda.pais")}>
        <select id="pais" value={form.pais} onChange={(e) => cambiar("pais", e.target.value)}>
          {PAISES.map((p) => <option key={p} value={p}>{t(`paises.${p}`)}</option>)}
        </select>
      </Campo>
      <Campo id="ciiu" etiqueta={t("busqueda.actividad")}>
        <select id="ciiu" value={form.ciiu} onChange={(e) => cambiar("ciiu", e.target.value)}>
          <option value="">{t("busqueda.actividad_vacia")}</option>
          {actividades.map((a) => <option key={a.codigo} value={a.codigo}>{nombre(a)}</option>)}
        </select>
      </Campo>
      {departamento}
      {ingresosMin}
      {palabrasClave}
      {exclusiones}
      <Campo id="canal" etiqueta={t("busqueda.canal")}>
        <select id="canal" value={form.canal} onChange={(e) => cambiar("canal", e.target.value)}>
          {CANALES.map((c) => <option key={c} value={c}>{t(`canales.${c}`)}</option>)}
        </select>
      </Campo>
      {tope}
      <Campo id="mensaje" etiqueta={t("busqueda.mensaje")}>
        <textarea id="mensaje" value={form.mensaje} onChange={(e) => cambiar("mensaje", e.target.value)} />
      </Campo>

      <div className="acciones">
      <button
        type="button"
        className="boton"
        disabled={!form.ciiu || !(Number(form.tope) > 0)}
        onClick={() => intentar(async () => setVista(await vistaPrevia(aPedido(form))))}
      >
        {t("busqueda.vista_previa")}
      </button>
      </div>
      {vista && <ResultadoVistaPrevia vista={vista} tope={Number(form.tope)} />}
      <div className="acciones">
      <button
        type="button"
        className="boton boton-primario"
        disabled={!puedeBuscar}
        onClick={() =>
          intentar(async () => {
            await ejecutar(vista!.busqueda_id);
            navegar("/tablero");
          })
        }
      >
        {t("busqueda.buscar")}
      </button>
      </div>
      {fallo && <p role="alert" className="error">{t("busqueda.error")}</p>}
      </div>
    </main>
  );
}
