import { useEffect, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import Atribuciones from "../compartido/Atribuciones";
import Esqueleto from "../compartido/Esqueleto";
import Trabajando from "../compartido/Trabajando";
import { ErrorApi } from "../api/cliente";
import Enlace from "../compartido/Enlace";
import { RUTA_BUSQUEDAS, RUTA_LEADS } from "../compartido/rutas";
import { entero, moneda, monedaFina, porcentaje } from "../compartido/formato";
import { obtenerCpql, exportarParaDapta, importarDeDapta, obtenerTablero } from "./api";
import type { Cpql, FilaCpql, FilaTablero, ResumenImportacion, Tablero as DatosTablero } from "./tipos";

type Columna =
  | "costo_lista" | "costo_real" | "desperdicio_lista" | "desperdicio_real" | "cpl_lista" | "cpl_real" | "naturales"
  | "calificados" | "pct_calificados" | "cpql";

const SIN_ATRIBUIR = "sin_atribuir";

type PropsFila = { fila: FilaTablero; total?: boolean; columnas: Columna[]; cpql?: FilaCpql };

function Fila({ fila, total = false, columnas, cpql }: PropsFila) {
  const { t } = useTranslation();
  const sinAtribuir = fila.fuente === SIN_ATRIBUIR;
  // "Sin atribuir" es costo sin fuente: no tiene calificados, % ni CPQL propios (el costo sí, en sus columnas).
  const calificados = cpql?.calificados ?? null;
  const celdas: Record<Columna, string> = {
    costo_lista: moneda(fila.costo_lista),
    costo_real: moneda(fila.costo_real),
    desperdicio_lista: moneda(fila.desperdicio_lista),
    desperdicio_real: moneda(fila.desperdicio_real),
    cpl_lista: moneda(fila.cpl_lista),
    cpl_real: moneda(fila.cpl_real),
    naturales: total ? "" : fila.cuenta_naturales ? entero(fila.naturales_no_contactables) : t("tablero.no_aplica"),
    calificados: sinAtribuir ? "" : entero(calificados),
    pct_calificados: sinAtribuir ? "" : porcentaje(calificados, fila.unicos),
    cpql: sinAtribuir ? "" : monedaFina(cpql?.cpql_lista ?? null),
  };
  const nombre = total ? t("tablero.total") : t(`fuentes.${fila.fuente}`);
  // Cada fila lleva a sus leads; "sin atribuir" son costos sin lead, no hay lista.
  const etiqueta = sinAtribuir ? nombre : (
    <Enlace a={total ? RUTA_LEADS : `${RUTA_LEADS}?fuente=${encodeURIComponent(fila.fuente)}`}>{nombre}</Enlace>
  );
  return (
    <tr className={total ? "total" : sinAtribuir ? "sin-atribuir" : undefined}>
      <td>{etiqueta}</td>
      <td>{entero(fila.encontrados)}</td>
      <td>{entero(fila.unicos)}</td>
      {columnas.map((c) => <td key={c}>{celdas[c]}</td>)}
    </tr>
  );
}

/** Solo las columnas que la API ya calcula: lo que viene null en toda la tabla no se pinta (no hay columna de "—"). */
function columnasConDatos(d: DatosTablero, cpql: Cpql | null): Columna[] {
  const filas = [...d.fuentes, d.total];
  const hay = (c: keyof FilaTablero) => filas.some((f) => f[c] !== null);
  const columnas: Columna[] = [];
  const conCostos = hay("costo_lista");
  if (conCostos) columnas.push("costo_lista", "costo_real");
  if (hay("desperdicio_lista")) columnas.push("desperdicio_lista", "desperdicio_real");
  if (conCostos) columnas.push("cpl_lista", "cpl_real");  // con costos, el CPL sin divisor se ve como "—"
  if (filas.some((f) => f.cuenta_naturales)) columnas.push("naturales");
  if (cpql?.fuentes.length) columnas.push("calificados", "pct_calificados", "cpql");
  return columnas;
}

const PASOS_EMBUDO = [
  ["encontrados", "tablero.encontrados"],
  ["unicos", "tablero.unicos"],
  ["enriquecidos", "tablero.embudo_enriquecidos"],
  ["contactables", "tablero.embudo_contactables"],
  ["con_telefono", "tablero.embudo_con_telefono"],
  ["calificados", "tablero.embudo_calificados"],
] as const;

const CAMPOS_NUEVOS = ["enriquecidos", "contactables", "con_telefono", "calificados"] as const;

/** Ancho de la barra: proporción de únicos, tope 100 (encontrados puede superar a únicos); sin dato o sin únicos, 0. */
function anchoBarra(valor: number | null, unicos: number): string {
  if (valor === null || !unicos) return "0%";
  return `${Math.min(100, Math.round((valor / unicos) * 100))}%`;
}

function EmbudoFuente({ fila, total = false }: { fila: FilaTablero; total?: boolean }) {
  const { t } = useTranslation();
  const nombre = total ? t("tablero.total") : t(`fuentes.${fila.fuente}`);
  return (
    <div role="group" aria-label={nombre} className="embudo-fuente">
      <h3>{nombre}</h3>
      <ul className="embudo-pasos">
        {PASOS_EMBUDO.map(([campo, etiqueta]) => {
          const valor = fila[campo] ?? null;  // un backend sin el campo es "sin dato", no cero
          return (
            <li key={campo} className="embudo-paso">
              <span data-paso="etiqueta" className="embudo-etiqueta">{t(etiqueta)}</span>
              <span data-paso="valor" className="embudo-valor">{entero(valor)}</span>
              <span data-paso="pct" className="embudo-pct">{porcentaje(valor, fila.unicos)}</span>
              <span className="embudo-pista" aria-hidden="true">
                <span className="embudo-barra" style={{ width: anchoBarra(valor, fila.unicos) }} />
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Embudo({ datos }: { datos: DatosTablero }) {
  const { t } = useTranslation();
  const fuentes = datos.fuentes.filter((f) => f.fuente !== SIN_ATRIBUIR);  // costo sin lead: no tiene embudo
  // Como las columnas de la tabla: si la API no manda ningún dato del embudo (backend viejo), no se pinta una sección de "—".
  const hayDatos = [...fuentes, datos.total].some((f) => CAMPOS_NUEVOS.some((c) => (f[c] ?? null) !== null));
  if (!fuentes.length || !hayDatos) return null;
  return (
    <section className="embudo" aria-labelledby="embudo-titulo">
      <h2 id="embudo-titulo">{t("tablero.embudo")}</h2>
      <p className="embudo-ayuda">{t("tablero.embudo_ayuda")}</p>
      {fuentes.map((f) => <EmbudoFuente key={f.fuente} fila={f} />)}
      <EmbudoFuente fila={datos.total} total />
    </section>
  );
}

/** Filas que quedaron afuera por cualquier motivo: a la persona le importa que hay que revisar el archivo. */
const omitidas = (r: ResumenImportacion) => r.rechazadas.length + r.conflictos + r.no_cumple + r.ref_desconocida;

const ERRORES_IMPORTAR = [409, 413, 415, 422, 503];

export default function Tablero() {
  const { t } = useTranslation();
  const [datos, setDatos] = useState<DatosTablero | null>(null);
  const [fallo, setFallo] = useState(false);
  const [cpql, setCpql] = useState<Cpql | null>(null);
  const [falloExport, setFalloExport] = useState(false);
  const [importando, setImportando] = useState(false);
  const [resumen, setResumen] = useState<ResumenImportacion | null>(null);
  const [falloImportar, setFalloImportar] = useState<string | null>(null);

  const cargarCpql = () => obtenerCpql().then(setCpql).catch(() => setCpql(null));

  useEffect(() => {
    obtenerTablero().then(setDatos).catch(() => setFallo(true));
    // El CPQL es un agregado: si falla, el tablero se ve como sin él (sin columnas nuevas, sin error).
    void cargarCpql();
  }, []);

  const importar = async (e: ChangeEvent<HTMLInputElement>) => {
    const entrada = e.target;
    const archivo = entrada.files?.[0];
    if (!archivo) return;
    setResumen(null);
    setFalloImportar(null);
    setImportando(true);
    try {
      setResumen(await importarDeDapta(archivo));
      await Promise.all([obtenerTablero().then(setDatos).catch(() => undefined), cargarCpql()]);
    } catch (error) {
      const estado = error instanceof ErrorApi ? error.estado : 0;
      setFalloImportar(ERRORES_IMPORTAR.includes(estado) ? `error_importar_${estado}` : "error_importar");
    } finally {
      setImportando(false);
      entrada.value = "";  // para poder subir de nuevo el mismo archivo
    }
  };

  if (!datos) {
    return (
      <main className="pantalla pantalla-ancha">
        <h1>{t("tablero.titulo")}</h1>
        {fallo ? <p role="alert" className="error">{t("tablero.error")}</p> : <Esqueleto filas={5} />}
      </main>
    );
  }
  // La API manda null en todo lo que aún no calcula: esas columnas y secciones no se pintan.
  const extra = columnasConDatos(datos, cpql);
  const cpqlPorFuente = new Map(cpql?.fuentes.map((f) => [f.fuente, f]));
  // "Sin atribuir" va al final, antes del total.
  const fuentes = [...datos.fuentes.filter((f) => f.fuente !== SIN_ATRIBUIR), ...datos.fuentes.filter((f) => f.fuente === SIN_ATRIBUIR)];
  const columnas = ["fuente", "encontrados", "unicos", ...extra];
  return (
    <main className="pantalla pantalla-ancha">
      <h1>{t("tablero.titulo")}</h1>
      <div className="acciones acciones-fin">
        <Enlace a={RUTA_BUSQUEDAS}>{t("tablero.ver_busquedas")}</Enlace>
        <button type="button" className="boton" onClick={() => exportarParaDapta().catch(() => setFalloExport(true))}>
          {t("tablero.exportar_dapta")}
        </button>
      </div>
      <div className="importar-dapta">
        <label>
          {t("tablero.importar_dapta")}
          <input type="file" accept=".csv,text/csv" disabled={importando} onChange={importar} />
        </label>
      </div>
      {importando && <Trabajando texto={t("tablero.importando")} />}
      {resumen && (
        <p role="status" className="aviso importar-resumen">
          {t("tablero.importar_listo", { count: resumen.importadas })}
          {resumen.duplicadas > 0 && ` ${t("tablero.importar_repetidas", { count: resumen.duplicadas })}`}
          {omitidas(resumen) > 0 && ` ${t("tablero.importar_omitidas", { count: omitidas(resumen) })}`}
        </p>
      )}
      {falloImportar && <p role="alert" className="error">{t(`tablero.${falloImportar}`)}</p>}
      {falloExport && <p role="alert" className="error">{t("tablero.error_exportar")}</p>}
      <div className="tabla-scroll">
      <table>
        <thead>
          <tr>
            {columnas.map((c) => <th key={c}>{t(`tablero.${c}`)}</th>)}
          </tr>
        </thead>
        <tbody>
          {fuentes.map((f) => <Fila key={f.fuente} fila={f} columnas={extra} cpql={cpqlPorFuente.get(f.fuente)} />)}
          <Fila fila={datos.total} total columnas={extra} cpql={cpql?.total ?? undefined} />
        </tbody>
      </table>
      </div>
      <Embudo datos={datos} />
      {(datos.costo_evals !== null || datos.revisiones_pendientes !== null) && (
        <div className="metricas">
          {datos.costo_evals !== null && (
            <p className="metrica">{t("tablero.costo_evals", { monto: moneda(datos.costo_evals) })}</p>
          )}
          {datos.revisiones_pendientes !== null && (
            <p className="metrica">{t("tablero.revisiones_pendientes", { n: entero(datos.revisiones_pendientes) })}</p>
          )}
        </div>
      )}
      {datos.cobertura !== null && (
        <>
          <h2>{t("tablero.cobertura")}</h2>
          <ul className="lista">
            {datos.cobertura.map((c) => (
              <li key={c.pais}>{c.pais}: {c.fuentes.map((f) => t(`fuentes.${f}`)).join(", ")}</li>
            ))}
          </ul>
        </>
      )}
      <Atribuciones atribuciones={datos.atribuciones} />
    </main>
  );
}
