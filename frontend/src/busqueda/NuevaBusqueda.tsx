import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ErrorApi } from "../api/cliente";
import { navegar } from "../compartido/navegar";
import {
  divisionesDe, ejecutar, estadoIntake, listarActividades, listarPaises, sugerirDesdeFrase, vistaPrevia,
  type EstadoIntake, type Sugerencia,
} from "./api";
import ResultadoVistaPrevia from "./ResultadoVistaPrevia";
import type { Actividad, Division, PedidoVistaPrevia, VistaPrevia } from "./tipos";

const CANALES = ["email"];

type Formulario = Record<
  "pais" | "ciiu" | "departamento" | "ciudad" | "ingresosMin" | "palabrasClave" | "exclusiones" | "canal" | "tope" | "mensaje",
  string
>;
const INICIAL: Formulario = {
  pais: "CO", ciiu: "", departamento: "", ciudad: "", ingresosMin: "", palabrasClave: "",
  exclusiones: "", canal: "email", tope: "", mensaje: "",
};

type Pestana = "lookalike" | "frase" | "filtros";
const MAX_FRASE = 500;

/** La sugerencia de una puerta pisa solo los criterios del ICP; canal, tope y mensaje son del usuario. */
function conSugerencia(f: Formulario, s: Sugerencia): Formulario {
  return {
    ...f,
    pais: s.pais,
    ciiu: s.ciiu ?? "",
    departamento: s.departamento ?? "",
    ciudad: s.departamento && s.ciudad ? s.ciudad : "",
    ingresosMin: s.ingresos_min === null ? "" : String(s.ingresos_min),
    palabrasClave: s.palabras_clave.join(", "),
    exclusiones: s.exclusiones.join(", "),
  };
}

const lista = (texto: string) => texto.split(",").map((p) => p.trim()).filter(Boolean);

function aPedido(f: Formulario): PedidoVistaPrevia {
  return {
    pais: f.pais,
    ciiu: f.ciiu,
    // Códigos, no nombres. La ciudad solo viaja dentro de una división (el select de división lo garantiza).
    departamento: f.departamento || undefined,
    ciudad: f.departamento && f.ciudad.trim() ? f.ciudad.trim() : undefined,
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
  const [paises, setPaises] = useState<string[]>([]);
  const [divisiones, setDivisiones] = useState<Division[]>([]);
  const [fallo, setFallo] = useState(false);
  const [puertas, setPuertas] = useState<EstadoIntake>({ frase: false, lookalike: false });
  const [pestana, setPestana] = useState<Pestana>("filtros");
  const [frase, setFrase] = useState("");
  const [pensando, setPensando] = useState(false);
  const [errorFrase, setErrorFrase] = useState<string | null>(null);
  const [sugerido, setSugerido] = useState(false);

  useEffect(() => {
    // Sin estado (o si falla) solo queda Filtros: las puertas son un atajo, no un requisito.
    estadoIntake().then(setPuertas).catch(() => undefined);
    listarActividades().then(setActividades).catch(() => undefined);
    // Solo se ofrecen los países que tienen archivo de geografía.
    listarPaises().then((r) => setPaises(r.paises)).catch(() => undefined);
  }, []);

  useEffect(() => {
    let vigente = true;
    setDivisiones([]);
    divisionesDe(form.pais).then((r) => vigente && setDivisiones(r.divisiones)).catch(() => undefined);
    return () => {
      vigente = false;
    };
  }, [form.pais]);

  // Cualquier cambio invalida la vista previa: el borrador congeló otros criterios.
  function cambiar(campo: keyof Formulario, valor: string) {
    // Cascada país -> división -> ciudad: cambiar un nivel suelta lo de abajo (sus códigos no valen en otro).
    const sueltan: Partial<Formulario> =
      campo === "pais" ? { departamento: "", ciudad: "" } : campo === "departamento" ? { ciudad: "" } : {};
    setForm((f) => ({ ...f, [campo]: valor, ...sueltan }));
    setVista(null);
  }

  async function sugerir() {
    setErrorFrase(null);
    setPensando(true);
    try {
      const { sugerencia } = await sugerirDesdeFrase(frase.trim());
      setForm((f) => conSugerencia(f, sugerencia));
      setVista(null);
      setSugerido(true);
      setPestana("filtros");  // el usuario revisa y edita antes de gastar en vista previa
    } catch (e) {
      setErrorFrase(e instanceof ErrorApi && e.estado === 503 ? "error_no_disponible" : "error_interpretacion");
    } finally {
      setPensando(false);
    }
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
  const division = divisiones.find((d) => d.codigo_nativo === form.departamento);
  const etiquetaDivision = t(`geografia.division.${form.pais}`, { defaultValue: t("busqueda.departamento") });
  const ingresosMin = entrada("ingresosMin", t("busqueda.ingresos_min"), "number");
  const palabrasClave = entrada("palabrasClave", t("busqueda.palabras_clave"));
  const exclusiones = entrada("exclusiones", t("busqueda.exclusiones"));
  const tope = entrada("tope", t("busqueda.tope"), "number");
  const nombre = (a: Actividad) => (i18n.language === "en" ? a.nombre_en ?? a.nombre_es : a.nombre_es);
  const pestanas: Pestana[] = [
    ...(puertas.lookalike ? (["lookalike"] as const) : []),
    ...(puertas.frase ? (["frase"] as const) : []),
    "filtros",
  ];
  const puedeBuscar = vista !== null && vista.dentro_del_tope !== false && vista.fuentes.length > 0;

  return (
    <main className="pantalla">
      <h1>{t("busqueda.titulo")}</h1>
      {pestanas.length > 1 && (
        <div role="tablist" className="pestanas">
          {pestanas.map((p) => (
            <button key={p} type="button" role="tab" aria-selected={pestana === p} className="pestana"
              onClick={() => setPestana(p)}>
              {t(`busqueda.pestanas.${p}`)}
            </button>
          ))}
        </div>
      )}
      {pestana === "frase" && (
        <div className="formulario formulario-ancho" role="tabpanel">
          <Campo id="frase" etiqueta={t("busqueda.frase.etiqueta")}>
            <textarea id="frase" maxLength={MAX_FRASE} value={frase} onChange={(e) => setFrase(e.target.value)} />
          </Campo>
          <p className="ayuda">{t("busqueda.frase.ayuda")}</p>
          <div className="acciones">
            <button type="button" className="boton boton-primario" disabled={!frase.trim() || pensando} onClick={sugerir}>
              {pensando ? t("busqueda.frase.pensando") : t("busqueda.frase.sugerir")}
            </button>
          </div>
          {errorFrase && <p role="alert" className="error">{t(`busqueda.frase.${errorFrase}`)}</p>}
        </div>
      )}
      {pestana === "lookalike" && <div className="formulario formulario-ancho" role="tabpanel" />}
      {pestana === "filtros" && (
      <div className="formulario formulario-ancho">
      {sugerido && <p role="status" className="aviso">{t("busqueda.frase.revisar")}</p>}
      <Campo id="pais" etiqueta={t("busqueda.pais")}>
        <select id="pais" value={form.pais} onChange={(e) => cambiar("pais", e.target.value)}>
          {paises.map((p) => <option key={p} value={p}>{t(`paises.${p}`)}</option>)}
        </select>
      </Campo>
      <Campo id="ciiu" etiqueta={t("busqueda.actividad")}>
        <select id="ciiu" value={form.ciiu} onChange={(e) => cambiar("ciiu", e.target.value)}>
          <option value="">{t("busqueda.actividad_vacia")}</option>
          {actividades.map((a) => <option key={a.codigo} value={a.codigo}>{nombre(a)}</option>)}
        </select>
      </Campo>
      {divisiones.length > 0 && (
        <Campo id="departamento" etiqueta={etiquetaDivision}>
          <select id="departamento" value={form.departamento} onChange={(e) => cambiar("departamento", e.target.value)}>
            <option value="">{t("busqueda.departamento_vacio")}</option>
            {divisiones.map((d) => (
              <option key={d.codigo_nativo} value={d.codigo_nativo}>{i18n.language === "en" ? d.nombre_en : d.nombre_es}</option>
            ))}
          </select>
        </Campo>
      )}
      <Campo id="ciudad" etiqueta={t("busqueda.ciudad")}>
        <input
          id="ciudad"
          type="text"
          list="ciudades"
          autoComplete="off"
          disabled={!division || division.municipios.length === 0}
          value={form.ciudad}
          onChange={(e) => cambiar("ciudad", e.target.value)}
        />
        <datalist id="ciudades">
          {(division?.municipios ?? []).map((m) => <option key={m.codigo_nativo} value={m.nombre} />)}
        </datalist>
      </Campo>
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
      )}
    </main>
  );
}
