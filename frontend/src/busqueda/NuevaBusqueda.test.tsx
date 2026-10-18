import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ComponentType } from "react";
import { afterEach, expect, test, vi } from "vitest";
import App from "../App";
import i18n from "../i18n";
import en from "../i18n/en.json";
import es from "../i18n/es.json";
import {
  actividades,
  boton,
  campo,
  espiarFijarIdioma,
  manejarGeografia,
  iniciarSesion,
  monto,
  respuestaVistaPrevia,
  respuestaVistaPreviaMinima,
} from "../test/fixtures";
import { server } from "../test/servidor";
import NuevaBusqueda from "./NuevaBusqueda";

afterEach(() => vi.restoreAllMocks());

/** Monta, llena lo mínimo y pide la vista previa. Devuelve los body que llegaron a vista-previa. */
async function previsualizar(
  vista: Record<string, unknown> = respuestaVistaPrevia(),
  tope = "5",
  Pantalla: ComponentType = NuevaBusqueda,
  antes: () => void | Promise<void> = () => undefined,
) {
  const pedidos: unknown[] = [];
  server.use(
    http.get("*/actividades", () => HttpResponse.json(actividades)),
    manejarGeografia(),
    http.post("*/busquedas/vista-previa", async ({ request }) => {
      pedidos.push(await request.json());
      return HttpResponse.json(vista);
    }),
  );
  const vistaMontada = render(<Pantalla />);
  await waitFor(() =>
    expect(screen.queryByRole("option", { name: es.busqueda.actividad_vacia })).toBeInTheDocument(),
  );
  await waitFor(() => expect(screen.queryByRole("option", { name: actividades[0].nombre_es })).toBeInTheDocument());
  fireEvent.change(campo("Actividad"), { target: { value: "1081" } });
  fireEvent.change(campo("Palabras clave (separadas por coma)"), { target: { value: "pan, harina" } });
  fireEvent.change(campo("Tope de gasto (USD)"), { target: { value: tope } });
  await antes();
  fireEvent.click(boton("Vista previa"));
  await waitFor(() => expect(pedidos).toHaveLength(1));
  return { pedidos, vistaMontada };
}

const fila = (nombre: string) =>
  screen.queryAllByRole("listitem").find((li) => li.textContent?.includes(nombre));

test("muestra_conteo_y_motivo_por_fuente", async () => {
  const { pedidos } = await previsualizar(
    respuestaVistaPrevia({
      fuentes: [
        { fuente: "croma_supersociedades_co", conteo: 100, motivo: null, ignorados: [], truncado: true },
        { fuente: "osm_overpass", conteo: 7, motivo: null, ignorados: ["ingresos_min"], truncado: false },
        { fuente: "datos_gov_co_rues", conteo: null, motivo: "sin_geografia", ignorados: [], truncado: false },
      ],
      descartadas: [{ fuente: "croma_dian_trade_co", motivo: "sin_mapeo_actividad" }],
    }),
  );

  expect(pedidos[0]).toEqual({
    pais: "CO",
    ciiu: "1081",
    palabras_clave: ["pan", "harina"],
    exclusiones: [],
    canal_preferido: "email",
    tope_gasto_usd: 5,
    mensaje_base: "",
  });
  await waitFor(() => expect(fila("OpenStreetMap")).toBeDefined());
  expect(fila("Supersociedades")).toHaveTextContent("100");
  expect(fila("OpenStreetMap")).toHaveTextContent("7");
  expect(fila("OpenStreetMap")).toHaveTextContent("Ingresos mínimos");
  expect(fila("RUES")).toHaveTextContent(es.motivos.sin_geografia);
  expect(fila("DIAN")).toHaveTextContent(es.motivos.sin_mapeo_actividad);
});

test("aclara_que_el_conteo_es_antes_de_palabras_clave", async () => {
  await previsualizar();
  await waitFor(() =>
    expect(screen.queryByText(es.busqueda.conteo_antes_de_filtros)).toBeInTheDocument(),
  );
});

test("buscar_deshabilitado_si_costo_maximo_supera_tope", async () => {
  // El estimado cabe en el tope (0.90 ≤ 1) y el máximo no (1.40 > 1): solo el máximo decide.
  await previsualizar(
    respuestaVistaPrevia({
      costo_estimado_usd: "0.9000",
      costo_maximo_usd: "1.4000",
      dentro_del_tope: false,
    }),
    "1",
  );
  await waitFor(() => expect(screen.queryByText(`Costo estimado: ${monto("es", "0.9")}`)).toBeInTheDocument());
  expect(screen.queryByText(`Costo máximo: ${monto("es", "1.4")}`)).toBeInTheDocument();
  expect(screen.queryByText(`Tope: ${monto("es", "1")}`)).toBeInTheDocument();
  expect(screen.queryByText(es.busqueda.se_compara_el_maximo)).toBeInTheDocument();
  expect(boton("Buscar")).toBeDisabled();
});

test("buscar_habilitado_si_costo_maximo_esta_dentro_del_tope", async () => {
  await previsualizar(respuestaVistaPrevia({ dentro_del_tope: true }));
  await waitFor(() => expect(boton("Buscar")).toBeEnabled());
});

test("buscar_deshabilitado_si_ninguna_fuente_cubre", async () => {
  await previsualizar(
    respuestaVistaPrevia({
      fuentes: [],
      descartadas: [{ fuente: "osm_overpass", motivo: "pais" }],
      dentro_del_tope: true,
    }),
  );
  await waitFor(() => expect(screen.queryByText(es.busqueda.ninguna_fuente_cubre)).toBeInTheDocument());
  expect(boton("Buscar")).toBeDisabled();
});

test("cambiar_un_filtro_invalida_la_vista_previa", async () => {
  await previsualizar();
  await waitFor(() => expect(boton("Buscar")).toBeEnabled());

  fireEvent.change(campo("Exclusiones (separadas por coma)"), { target: { value: "integral" } });

  expect(boton("Buscar")).toBeDisabled();
  expect(fila("OpenStreetMap")).toBeUndefined();
});

test("buscar_ejecuta_sin_body_y_lleva_al_tablero", async () => {
  const ejecuciones: string[] = [];
  server.use(
    http.post("*/busquedas/:id/ejecutar", async ({ request, params }) => {
      ejecuciones.push(`${params.id}|${await request.text()}`);
      return HttpResponse.json({ estado: "completada" });
    }),
  );
  await previsualizar();
  await waitFor(() => expect(boton("Buscar")).toBeEnabled());

  fireEvent.click(boton("Buscar"));

  await waitFor(() => expect(location.pathname).toBe("/tablero"));
  expect(ejecuciones).toEqual(["b-1|"]);
});

test("cambia_idioma", async () => {
  vi.spyOn(navigator, "languages", "get").mockReturnValue(["es-CO"]);
  iniciarSesion({ usuario: null, tenant: "es" });
  history.pushState(null, "", "/busqueda/nueva");
  const patches = espiarFijarIdioma();
  const vista = respuestaVistaPrevia({ descartadas: [{ fuente: "croma_dian_trade_co", motivo: "sin_mapeo_actividad" }] });

  const { vistaMontada } = await previsualizar(vista, "5", App);
  // Arranca en es: navegador es-CO, sin elección guardada, tenant es.
  expect(i18n.language).toBe("es");
  expect(boton("Buscar")).toBeInTheDocument();

  fireEvent.change(campo("Idioma"), { target: { value: "en" } });

  await waitFor(() => expect(patches).toEqual([{ idioma: "en" }]));
  await waitFor(() => expect(boton(en.busqueda.buscar)).toBeInTheDocument());
  expect(campo(en.busqueda.tope)).toBeInTheDocument();
  expect(screen.queryByText(en.motivos.sin_mapeo_actividad, { exact: false })).toBeInTheDocument();
  expect(screen.queryByText(en.busqueda.tope_linea.replace("{{monto}}", monto("en", 5)))).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: actividades[0].nombre_en! })).toBeInTheDocument();
  // Sin nombre_en cae a nombre_es.
  expect(screen.queryByRole("option", { name: actividades[1].nombre_es })).toBeInTheDocument();
  expect(sessionStorage.getItem("idioma_usuario")).toBe("en");

  // i18next es un singleton: sin esto seguiría en en por inercia y simularía una carga en frío.
  vistaMontada.unmount();
  await i18n.changeLanguage("es");
  server.use(
    http.get("*/actividades", () => HttpResponse.json(actividades)),
    manejarGeografia(),
  );
  render(<App />);
  await waitFor(() => expect(boton(en.busqueda.buscar)).toBeInTheDocument());
  expect(patches).toHaveLength(1);
});

test("vista_previa_exige_actividad_y_tope", async () => {
  server.use(
    http.get("*/actividades", () => HttpResponse.json(actividades)),
    manejarGeografia(),
  );
  render(<NuevaBusqueda />);
  await waitFor(() => expect(screen.queryByRole("option", { name: actividades[0].nombre_es })).toBeInTheDocument());
  expect(boton("Vista previa")).toBeDisabled();

  fireEvent.change(campo("Actividad"), { target: { value: "1081" } });
  expect(boton("Vista previa")).toBeDisabled();
  fireEvent.change(campo("Tope de gasto (USD)"), { target: { value: "5" } });
  expect(boton("Vista previa")).toBeEnabled();
});

test("un_error_de_la_api_se_avisa_y_no_deja_la_busqueda_a_medias", async () => {
  server.use(http.post("*/busquedas/:id/ejecutar", () => new HttpResponse(null, { status: 409 })));
  await previsualizar();
  await waitFor(() => expect(boton("Buscar")).toBeEnabled());

  fireEvent.click(boton("Buscar"));

  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent("No se pudo completar la operación. Probá de nuevo."));
  expect(location.pathname).toBe("/");
});

test("un_error_en_la_vista_previa_se_avisa", async () => {
  server.use(
    http.get("*/actividades", () => HttpResponse.json(actividades)),
    manejarGeografia(),
    http.post("*/busquedas/vista-previa", () => new HttpResponse(null, { status: 422 })),
  );
  render(<NuevaBusqueda />);
  await waitFor(() => expect(screen.queryByRole("option", { name: actividades[0].nombre_es })).toBeInTheDocument());
  fireEvent.change(campo("Actividad"), { target: { value: "1081" } });
  fireEvent.change(campo("Tope de gasto (USD)"), { target: { value: "5" } });

  fireEvent.click(boton("Vista previa"));

  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent("No se pudo completar la operación. Probá de nuevo."));
});

test("vista_previa_sin_costos_habilita_buscar_y_no_muestra_costos_ni_tope", async () => {
  await previsualizar(respuestaVistaPreviaMinima());

  await waitFor(() => expect(fila("OpenStreetMap")).toBeDefined());
  // dentro_del_tope null = el tope no se evalúa: no bloquea (solo `false` bloquea).
  expect(boton("Buscar")).toBeEnabled();
  expect(fila("OpenStreetMap")).toHaveTextContent(es.motivos.sin_conteo);
  for (const clave of ["Costo estimado", "Costo máximo", "Tope:", "Créditos de Croma", "Consultas de Croma"]) {
    expect(screen.queryByText(new RegExp(clave))).not.toBeInTheDocument();
  }
  expect(screen.queryByText(es.busqueda.se_compara_el_maximo)).not.toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/NaN|—/);  // ni "sin dato" ni basura: las líneas no se pintan
});

test("los_ignorados_de_palabras_clave_exclusiones_y_ciudad_salen_con_su_nombre", async () => {
  await previsualizar(respuestaVistaPreviaMinima());

  await waitFor(() => expect(fila("OpenStreetMap")).toBeDefined());
  expect(fila("OpenStreetMap")).toHaveTextContent("Palabras clave, Exclusiones");
  expect(fila("RUES")).toHaveTextContent("Ciudad");
  expect(en.criterios.palabras_clave && en.criterios.exclusiones && en.criterios.ciudad).toBeTruthy();
});

const opcion = (nombre: string) => screen.queryByRole("option", { name: nombre });
const pedido0 = (pedidos: unknown[]) => pedidos[0] as Record<string, unknown>;

/** Monta con los países pedidos (por defecto solo CO), espera las actividades y las divisiones de CO. */
async function montarGeografia(paises = ["CO"]) {
  server.use(http.get("*/actividades", () => HttpResponse.json(actividades)), manejarGeografia(paises));
  render(<NuevaBusqueda />);
  await waitFor(() => expect(opcion("Tolima")).toBeInTheDocument());
}

test("la_division_es_un_select_que_manda_el_codigo_nativo_no_el_nombre", async () => {
  const { pedidos } = await previsualizar(respuestaVistaPrevia(), "5", NuevaBusqueda, async () => {
    await waitFor(() => expect(opcion("Tolima")).toBeInTheDocument());
    expect(campo("Departamento").tagName).toBe("SELECT");  // no texto libre
    fireEvent.change(campo("Departamento"), { target: { value: "73" } });
  });

  expect(pedido0(pedidos).departamento).toBe("73");  // el código nativo (DIVIPOLA), nunca "Tolima" ni "CO-TOL"
  expect(opcion("Bogotá, D.C.")).toBeInTheDocument();
});

test("sin_division_elegida_no_se_envia_ni_departamento_ni_ciudad", async () => {
  const { pedidos } = await previsualizar(respuestaVistaPrevia(), "5", NuevaBusqueda, async () => {
    await waitFor(() => expect(opcion("Tolima")).toBeInTheDocument());
  });
  expect(pedido0(pedidos)).not.toHaveProperty("departamento");
  expect(pedido0(pedidos)).not.toHaveProperty("ciudad");
});

test("la_ciudad_es_un_input_con_los_municipios_de_la_division_y_manda_el_nombre", async () => {
  const { pedidos } = await previsualizar(respuestaVistaPrevia(), "5", NuevaBusqueda, async () => {
    await waitFor(() => expect(opcion("Tolima")).toBeInTheDocument());
    fireEvent.change(campo("Departamento"), { target: { value: "73" } });
    const ciudad = campo(es.busqueda.ciudad);
    expect(ciudad.tagName).toBe("INPUT");  // autocompletado: input + datalist, no un select
    const lista = document.getElementById(ciudad.getAttribute("list") ?? "");
    expect([...(lista?.querySelectorAll("option") ?? [])].map((o) => o.getAttribute("value"))).toEqual(["Ibagué", "Melgar"]);
    fireEvent.change(ciudad, { target: { value: "Ibagué" } });
  });
  expect(pedido0(pedidos)).toMatchObject({ departamento: "73", ciudad: "Ibagué" });
});

test("la_ciudad_espera_a_la_division_y_se_borra_al_cambiarla", async () => {
  await montarGeografia();
  expect(campo(es.busqueda.ciudad)).toBeDisabled();  // si pone ciudad, la división es obligatoria: el select lo garantiza

  fireEvent.change(campo("Departamento"), { target: { value: "73" } });
  expect(campo(es.busqueda.ciudad)).toBeEnabled();
  fireEvent.change(campo(es.busqueda.ciudad), { target: { value: "Ibagué" } });
  fireEvent.change(campo("Departamento"), { target: { value: "05" } });

  expect(campo(es.busqueda.ciudad)).toHaveValue("");  // Ibagué no es de Antioquia
});

test("el_select_de_pais_solo_ofrece_los_paises_con_archivo", async () => {
  await montarGeografia(["CO"]);
  expect(opcion("Colombia")).toBeInTheDocument();
  for (const otro of ["México", "Brasil", "Perú"]) expect(opcion(otro)).not.toBeInTheDocument();
});

test("la_etiqueta_de_la_division_sale_por_pais_e_idioma", async () => {
  const etiquetas = (idioma: object) =>
    (idioma as { geografia?: { division?: Record<string, string> } }).geografia?.division ?? {};
  for (const [pais, esperado] of Object.entries({
    CO: ["Departamento", "Department"], MX: ["Estado", "State"], BR: ["Estado", "State"], PE: ["Departamento", "Region"],
  })) {
    expect([etiquetas(es)[pais], etiquetas(en)[pais]], pais).toEqual(esperado);
  }

  await montarGeografia(["CO", "PE"]);
  await waitFor(() => expect(opcion("Perú")).toBeInTheDocument());
  fireEvent.change(campo("Departamento"), { target: { value: "73" } });
  fireEvent.change(campo("País"), { target: { value: "PE" } });
  await waitFor(() => expect(opcion("Lima")).toBeInTheDocument());
  expect(campo("Departamento")).toHaveValue("");  // el código de Tolima no vale en Perú
  expect(opcion("Tolima")).not.toBeInTheDocument();

  await i18n.changeLanguage("en");
  await waitFor(() => expect(campo("Region")).toBeInTheDocument());
});

test("los_nombres_de_division_salen_en_el_idioma_activo", async () => {
  await i18n.changeLanguage("en");
  await montarGeografia();
  await waitFor(() => expect(opcion("San Andrés and Providencia")).toBeInTheDocument());
  expect(opcion("San Andrés y Providencia")).not.toBeInTheDocument();
  expect(campo(en.busqueda.ciudad)).toBeInTheDocument();
  expect(campo("Department")).toBeInTheDocument();
});
