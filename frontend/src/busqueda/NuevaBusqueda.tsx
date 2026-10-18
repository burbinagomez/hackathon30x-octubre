import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  divisionesDe, estadoIntake, listarActividades, listarPaises,
  type EstadoIntake, type Sugerencia,
} from "./api";
import BloqueBusqueda from "./BloqueBusqueda";
import ChatFrase from "./ChatFrase";
import { aPedido, conSugerencia, INICIAL, type Formulario } from "./formulario";
import IntakeLookalike from "./IntakeLookalike";
import type { Actividad, Division } from "./tipos";
import { useBusqueda } from "./useBusqueda";
import { useChatFrase } from "./useChatFrase";

const CANALES = ["email"];

type Pestana = "lookalike" | "frase" | "filtros";

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
  const filtros = useBusqueda();
  const chat = useChatFrase();
  const busquedaChat = useBusqueda();
  const [actividades, setActividades] = useState<Actividad[]>([]);
  const [paises, setPaises] = useState<string[]>([]);
  const [divisiones, setDivisiones] = useState<Division[]>([]);
  const [puertas, setPuertas] = useState<EstadoIntake>({ frase: false, lookalike: false });
  const [pestana, setPestana] = useState<Pestana>("filtros");
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
    filtros.reiniciar();
  }

  // Puerta A: prellena y se queda en su pestaña, porque ahí se ve la explicación (conteos y no resueltos).
  function aplicarLookalike(sugerencia: Sugerencia) {
    setForm((f) => conSugerencia(f, sugerencia));
    filtros.soltarVista();
    setSugerido(true);
  }

  // Del chat a Filtros: prellena los criterios y salta, para ajustarlos a mano. El tope viaja solo si la persona lo cambió.
  function editarEnFiltros(sugerencia: Sugerencia) {
    setForm((f) => ({ ...conSugerencia(f, sugerencia), ...(chat.topeEditado ? { tope: chat.tope } : {}) }));
    filtros.reiniciar();
    setSugerido(true);
    setPestana("filtros");  // el usuario revisa y edita antes de gastar en vista previa
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
        <ChatFrase chat={chat} busqueda={busquedaChat} actividades={actividades} alEditarEnFiltros={editarEnFiltros} />
      )}
      {pestana === "lookalike" && (
        <div className="panel-intake" role="tabpanel">
          {sugerido && <p role="status" className="aviso">{t("busqueda.frase.revisar")}</p>}
          <IntakeLookalike alSugerir={aplicarLookalike} />
        </div>
      )}
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

      <BloqueBusqueda busqueda={filtros} pedido={aPedido(form)} tope={Number(form.tope)}
        puedeVista={Boolean(form.ciiu) && Number(form.tope) > 0} />
      </div>
      )}
    </main>
  );
}
