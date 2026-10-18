import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import en from "../i18n/en.json";
import i18n from "../i18n";
import es from "../i18n/es.json";
import { actividades, boton, campo, manejarGeografia, respuestaVistaPrevia } from "../test/fixtures";
import { server } from "../test/servidor";
import NuevaBusqueda from "./NuevaBusqueda";

const FRASE = "vendo software contable a ferreterías medianas en Antioquia";
const PREGUNTA = "¿Vendés a ferreterías de qué tamaño?";
const EXPLICACION = "Busco ferreterías medianas en Antioquia porque venden insumos de obra.";
const SUGERENCIA = {
  pais: "CO",
  ciiu: "4631",
  departamento: "05",
  ciudad: "05001",
  ingresos_min: 500000000,
  palabras_clave: ["ferretería", "tornillos"],
  exclusiones: ["cadenas"],
};

type Estado = { frase: boolean; lookalike: boolean };

/** Monta Nueva búsqueda con el estado de las puertas dado. Devuelve los body que llegaron a /intake/frase y a vista-previa. */
async function montar(estado: Estado | "falla" = { frase: true, lookalike: false }, frase: () => Response | Promise<Response> = () => HttpResponse.json({ sugerencia: SUGERENCIA, pregunta: null, explicacion: EXPLICACION, costo_usd: "0.00005" })) {
  const frases: unknown[] = [];
  const vistas: unknown[] = [];
  server.use(
    http.get("*/intake/estado", () => (estado === "falla" ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(estado))),
    http.post("*/intake/frase", async ({ request }) => {
      frases.push(await request.json());
      return frase();
    }),
    http.get("*/actividades", () => HttpResponse.json(actividades)),
    manejarGeografia(),
    http.post("*/busquedas/vista-previa", async ({ request }) => {
      vistas.push(await request.json());
      return HttpResponse.json(respuestaVistaPrevia());
    }),
  );
  render(<NuevaBusqueda />);
  // En inglés la opción muestra nombre_en si existe: se espera la actividad en cualquiera de los dos idiomas.
  const nombres = [actividades[0].nombre_es, actividades[0].nombre_en].filter(Boolean) as string[];
  await waitFor(() => expect(nombres.some((n) => screen.queryByRole("option", { name: n }))).toBe(true));
  return { frases, vistas };
}

const pestana = (nombre: string) => screen.queryByRole("tab", { name: nombre });

function enviar(texto = FRASE) {
  fireEvent.change(campo(es.busqueda.frase.etiqueta), { target: { value: texto } });
  fireEvent.click(boton(es.busqueda.frase.enviar));
}

function escribirYSugerir(texto = FRASE) {
  fireEvent.click(pestana(es.busqueda.pestanas.frase)!);
  enviar(texto);
}

const conversacion = () => within(screen.getByRole("log"));
const verTarjeta = () => screen.findByRole("region", { name: es.busqueda.frase.voy_a_buscar });
const editarEnFiltros = async () => {
  await verTarjeta();
  fireEvent.click(boton(es.busqueda.frase.editar_en_filtros));
};

test("una_frase_clara_muestra_la_explicacion_y_la_tarjeta_voy_a_buscar_sin_saltar_a_filtros", async () => {
  const { frases, vistas } = await montar();

  escribirYSugerir();

  const tarjeta = await verTarjeta();
  expect(frases).toEqual([{ frase: FRASE, historial: [] }]);
  expect(pestana(es.busqueda.pestanas.frase)).toHaveAttribute("aria-selected", "true");
  expect(conversacion().getByText(FRASE)).toBeInTheDocument();
  expect(conversacion().getByText(EXPLICACION)).toBeInTheDocument();
  // Resumen legible: nombres, no códigos.
  const resumen = within(tarjeta);
  expect(resumen.getByText("Comercio al por mayor de alimentos")).toBeInTheDocument();
  expect(resumen.getByText("Antioquia")).toBeInTheDocument();
  expect(resumen.getByText("Medellín")).toBeInTheDocument();
  expect(resumen.getByText("ferretería, tornillos")).toBeInTheDocument();
  expect(resumen.getByText("cadenas")).toBeInTheDocument();
  expect(resumen.getByText(/500\.000\.000|500,000,000/)).toBeInTheDocument();
  expect(resumen.queryByText("05001")).not.toBeInTheDocument();
  expect(resumen.queryByText("4631")).not.toBeInTheDocument();
  // El tope arranca en 1 y nunca llama a la vista previa por sí misma.
  expect(campo(es.busqueda.tope)).toHaveValue(1);
  expect(vistas).toEqual([]);
});

test("editar_en_filtros_prellena_el_formulario_editable_y_salta_a_filtros", async () => {
  const { vistas } = await montar();
  escribirYSugerir();

  await editarEnFiltros();

  await waitFor(() => expect(pestana(es.busqueda.pestanas.filtros)).toHaveAttribute("aria-selected", "true"));
  await waitFor(() => expect(campo("Departamento")).toHaveValue("05"));  // las divisiones llegan después
  expect(campo("Actividad")).toHaveValue("4631");
  expect(campo("Ciudad (opcional)")).toHaveValue("05001");
  expect(campo("Ingresos mínimos (USD)")).toHaveValue(500000000);
  expect(campo("Palabras clave (separadas por coma)")).toHaveValue("ferretería, tornillos");
  expect(campo("Exclusiones (separadas por coma)")).toHaveValue("cadenas");
  expect(vistas).toEqual([]);
  expect(screen.queryByRole("status")).toHaveTextContent(es.busqueda.frase.revisar);

  // Editable: el usuario pisa lo sugerido y es lo editado lo que viaja.
  fireEvent.change(campo("Palabras clave (separadas por coma)"), { target: { value: "tornillos" } });
  fireEvent.change(campo("Tope de gasto (USD)"), { target: { value: "5" } });
  fireEvent.click(boton("Vista previa"));
  await waitFor(() => expect(vistas).toHaveLength(1));
  expect(vistas[0]).toEqual({
    pais: "CO", ciiu: "4631", departamento: "05", ciudad: "05001", ingresos_min: 500000000,
    palabras_clave: ["tornillos"], exclusiones: ["cadenas"], canal_preferido: "email", tope_gasto_usd: 5, mensaje_base: "",
  });
});

test("una_sugerencia_con_campos_null_deja_esos_campos_vacios", async () => {
  await montar({ frase: true, lookalike: false }, () =>
    HttpResponse.json({ sugerencia: { ...SUGERENCIA, ciiu: null, departamento: null, ciudad: null, ingresos_min: null, palabras_clave: [], exclusiones: [] }, pregunta: null, explicacion: null, costo_usd: "0" }));

  escribirYSugerir();
  await editarEnFiltros();

  await waitFor(() => expect(pestana(es.busqueda.pestanas.filtros)).toHaveAttribute("aria-selected", "true"));
  expect(campo("Actividad")).toHaveValue("");
  expect(campo("Ingresos mínimos (USD)")).toHaveValue(null);
  expect(campo("Palabras clave (separadas por coma)")).toHaveValue("");
});

test("sin_actividad_no_se_puede_hacer_la_vista_previa_y_dice_que_hacer", async () => {
  await montar({ frase: true, lookalike: false }, () =>
    HttpResponse.json({ sugerencia: { ...SUGERENCIA, ciiu: null }, pregunta: null, explicacion: EXPLICACION, costo_usd: "0" }));

  escribirYSugerir();

  await verTarjeta();
  expect(boton("Vista previa")).toBeDisabled();
  expect(screen.getByText(es.busqueda.frase.sin_actividad)).toBeInTheDocument();
});

test("la_sugerencia_no_pisa_canal_tope_ni_mensaje", async () => {
  await montar();
  fireEvent.change(campo("Tope de gasto (USD)"), { target: { value: "7" } });
  fireEvent.change(campo("Mensaje base"), { target: { value: "Hola" } });

  escribirYSugerir();
  await editarEnFiltros();

  await waitFor(() => expect(pestana(es.busqueda.pestanas.filtros)).toHaveAttribute("aria-selected", "true"));
  expect(campo("Tope de gasto (USD)")).toHaveValue(7);
  expect(campo("Mensaje base")).toHaveValue("Hola");
});

test("el_tope_editado_en_el_chat_viaja_a_filtros", async () => {
  await montar();
  escribirYSugerir();
  await verTarjeta();
  fireEvent.change(campo(es.busqueda.tope), { target: { value: "3" } });

  fireEvent.click(boton(es.busqueda.frase.editar_en_filtros));

  await waitFor(() => expect(campo("Actividad")).toHaveValue("4631"));
  expect(campo("Tope de gasto (USD)")).toHaveValue(3);
});

test("si_la_ia_pregunta_aparece_como_mensaje_y_el_segundo_envio_lleva_el_historial", async () => {
  let n = 0;
  const { frases } = await montar({ frase: true, lookalike: false }, () =>
    ++n === 1
      ? HttpResponse.json({ sugerencia: { ...SUGERENCIA, ciiu: null }, pregunta: PREGUNTA, explicacion: null, costo_usd: "0" })
      : HttpResponse.json({ sugerencia: SUGERENCIA, pregunta: null, explicacion: EXPLICACION, costo_usd: "0" }));

  escribirYSugerir("vendo software contable");

  await waitFor(() => expect(conversacion().getByText(PREGUNTA)).toBeInTheDocument());
  expect(conversacion().getByText("vendo software contable")).toBeInTheDocument();
  expect(conversacion().getByText(es.busqueda.frase.asistente)).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: es.busqueda.frase.voy_a_buscar })).not.toBeInTheDocument();  // aún no hay qué buscar
  expect(campo(es.busqueda.frase.etiqueta)).toHaveValue("");  // se responde en el mismo cuadro

  enviar("ferreterías medianas");

  await verTarjeta();
  expect(frases).toEqual([
    { frase: "vendo software contable", historial: [] },
    {
      frase: "ferreterías medianas",
      historial: [{ rol: "usuario", texto: "vendo software contable" }, { rol: "asistente", texto: PREGUNTA }],
    },
  ]);
  expect(conversacion().getByText(EXPLICACION)).toBeInTheDocument();
});

test("la_lista_de_mensajes_es_un_log_que_se_anuncia_con_cortesia", async () => {
  await montar();
  fireEvent.click(pestana(es.busqueda.pestanas.frase)!);

  expect(screen.getByRole("log")).toHaveAttribute("aria-live", "polite");
});

test("mientras_la_ia_lee_se_ve_la_pildora_y_el_boton_queda_deshabilitado", async () => {
  let responder: (r: Response) => void = () => undefined;
  await montar({ frase: true, lookalike: false }, () => new Promise<Response>((r) => { responder = r; }));

  escribirYSugerir();

  await waitFor(() => expect(screen.getByRole("status", { name: es.busqueda.trabajando.frase })).toBeInTheDocument());
  expect(boton(es.busqueda.frase.pensando)).toBeDisabled();
  responder(HttpResponse.json({ sugerencia: SUGERENCIA, pregunta: null, explicacion: EXPLICACION, costo_usd: "0" }));
  await verTarjeta();
  expect(screen.queryByRole("status", { name: es.busqueda.trabajando.frase })).not.toBeInTheDocument();
  expect(boton(es.busqueda.frase.enviar)).toBeDisabled();  // el cuadro quedó vacío
});

test("vista_previa_manda_la_sugerencia_con_el_tope_y_muestra_el_resultado_en_la_misma_pestana", async () => {
  const { vistas } = await montar();
  escribirYSugerir();
  await verTarjeta();
  fireEvent.change(campo(es.busqueda.tope), { target: { value: "4" } });

  fireEvent.click(boton("Vista previa"));

  await waitFor(() => expect(vistas).toHaveLength(1));
  expect(vistas[0]).toEqual({
    pais: "CO", ciiu: "4631", departamento: "05", ciudad: "05001", ingresos_min: 500000000,
    palabras_clave: ["ferretería", "tornillos"], exclusiones: ["cadenas"], canal_preferido: "email", tope_gasto_usd: 4, mensaje_base: "",
  });
  expect(await screen.findByText(es.busqueda.conteo_antes_de_filtros)).toBeInTheDocument();
  expect(pestana(es.busqueda.pestanas.frase)).toHaveAttribute("aria-selected", "true");
});

test("buscar_ejecuta_y_muestra_el_resultado_por_fuente_sin_cambiar_de_pestana", async () => {
  const ejecuciones: string[] = [];
  server.use(
    http.post("*/busquedas/:id/ejecutar", ({ params }) => {
      ejecuciones.push(String(params.id));
      return HttpResponse.json({
        busqueda_id: "b-1", estado: "completada",
        por_fuente: { osm_overpass: { estado: "con_resultados", encontrados: 12 } },
      });
    }),
  );
  await montar();
  escribirYSugerir();
  await verTarjeta();
  expect(boton("Buscar")).toBeDisabled();  // antes se calcula la vista previa
  fireEvent.click(boton("Vista previa"));
  await waitFor(() => expect(boton("Buscar")).toBeEnabled());

  fireEvent.click(boton("Buscar"));

  expect(await screen.findByText("OpenStreetMap: 12 empresas")).toBeInTheDocument();
  expect(ejecuciones).toEqual(["b-1"]);
  expect(pestana(es.busqueda.pestanas.frase)).toHaveAttribute("aria-selected", "true");
});

test("una_sugerencia_nueva_deja_sin_vigencia_la_vista_previa_de_la_anterior", async () => {
  await montar();
  escribirYSugerir();
  await verTarjeta();
  fireEvent.click(boton("Vista previa"));
  await screen.findByText(es.busqueda.conteo_antes_de_filtros);

  enviar("mejor ferreterías de Bogotá");

  await waitFor(() => expect(conversacion().getByText("mejor ferreterías de Bogotá")).toBeInTheDocument());
  await waitFor(() => expect(screen.queryByText(es.busqueda.conteo_antes_de_filtros)).not.toBeInTheDocument());
  expect(boton("Buscar")).toBeDisabled();
});

test("empezar_de_nuevo_limpia_la_conversacion_la_tarjeta_y_los_resultados", async () => {
  await montar();
  escribirYSugerir();
  await verTarjeta();
  fireEvent.click(boton("Vista previa"));
  await screen.findByText(es.busqueda.conteo_antes_de_filtros);

  fireEvent.click(boton(es.busqueda.frase.empezar_de_nuevo));

  expect(screen.queryByText(FRASE)).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: es.busqueda.frase.voy_a_buscar })).not.toBeInTheDocument();
  expect(screen.queryByText(es.busqueda.conteo_antes_de_filtros)).not.toBeInTheDocument();
  expect(campo(es.busqueda.frase.etiqueta)).toHaveValue("");
});

test("la_conversacion_sobrevive_a_un_paseo_por_filtros", async () => {
  await montar();
  escribirYSugerir();
  await verTarjeta();

  fireEvent.click(pestana(es.busqueda.pestanas.filtros)!);
  fireEvent.click(pestana(es.busqueda.pestanas.frase)!);

  expect(conversacion().getByText(EXPLICACION)).toBeInTheDocument();
  expect(screen.getByRole("region", { name: es.busqueda.frase.voy_a_buscar })).toBeInTheDocument();
});

test("a_los_doce_turnos_avisa_y_ofrece_empezar_de_nuevo", async () => {
  let n = 0;
  await montar({ frase: true, lookalike: false }, () =>
    HttpResponse.json({ sugerencia: { ...SUGERENCIA, ciiu: null }, pregunta: `pregunta ${++n}`, explicacion: null, costo_usd: "0" }));

  escribirYSugerir("uno");
  await screen.findByText("pregunta 1");
  for (let i = 2; i <= 5; i++) {
    enviar(`mensaje ${i}`);
    await screen.findByText(`pregunta ${i}`);
  }
  expect(screen.queryByText(es.busqueda.frase.limite_turnos)).not.toBeInTheDocument();  // 10 turnos: todavía hay lugar
  enviar("seis");
  await screen.findByText("pregunta 6");

  expect(screen.getByText(es.busqueda.frase.limite_turnos)).toBeInTheDocument();
  fireEvent.change(campo(es.busqueda.frase.etiqueta), { target: { value: "siete" } });
  expect(boton(es.busqueda.frase.enviar)).toBeDisabled();
  fireEvent.click(boton(es.busqueda.frase.empezar_de_nuevo));
  expect(screen.queryByText(es.busqueda.frase.limite_turnos)).not.toBeInTheDocument();
});

test("el_boton_de_enviar_exige_un_mensaje", async () => {
  await montar();
  fireEvent.click(pestana(es.busqueda.pestanas.frase)!);
  expect(boton(es.busqueda.frase.enviar)).toBeDisabled();

  fireEvent.change(campo(es.busqueda.frase.etiqueta), { target: { value: "   " } });
  expect(boton(es.busqueda.frase.enviar)).toBeDisabled();

  fireEvent.change(campo(es.busqueda.frase.etiqueta), { target: { value: FRASE } });
  expect(boton(es.busqueda.frase.enviar)).toBeEnabled();
});

test("filtros_es_la_pestana_por_defecto_y_la_de_frase_trae_su_texto", async () => {
  await montar();

  expect(pestana(es.busqueda.pestanas.filtros)).toHaveAttribute("aria-selected", "true");
  expect(campo("Actividad")).toBeInTheDocument();
  fireEvent.click(pestana(es.busqueda.pestanas.frase)!);
  expect(pestana(es.busqueda.pestanas.frase)).toHaveAttribute("aria-selected", "true");
  expect(campo(es.busqueda.frase.etiqueta)).toHaveAttribute("maxlength", "500");
  expect(screen.queryByLabelText("Actividad")).not.toBeInTheDocument();
});

test("puerta_b_oculta_si_frase_es_false", async () => {
  await montar({ frase: false, lookalike: false });

  expect(pestana(es.busqueda.pestanas.frase)).not.toBeInTheDocument();
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();  // solo queda Filtros: sin fila de pestañas
  expect(campo("Actividad")).toBeInTheDocument();
});

test("si_el_estado_falla_se_ve_solo_filtros", async () => {
  await montar("falla");

  expect(pestana(es.busqueda.pestanas.frase)).not.toBeInTheDocument();
  expect(pestana(es.busqueda.pestanas.lookalike)).not.toBeInTheDocument();
  expect(campo("Actividad")).toBeInTheDocument();
});

test("ya_me_compran_esta_oculta_si_lookalike_es_false_y_visible_si_es_true", async () => {
  await montar({ frase: true, lookalike: false });
  expect(pestana(es.busqueda.pestanas.lookalike)).not.toBeInTheDocument();
});

test("ya_me_compran_aparece_cuando_lookalike_es_true", async () => {
  await montar({ frase: true, lookalike: true });

  expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
    es.busqueda.pestanas.lookalike, es.busqueda.pestanas.frase, es.busqueda.pestanas.filtros,
  ]);
  expect(pestana(es.busqueda.pestanas.filtros)).toHaveAttribute("aria-selected", "true");
});

test("la_ia_no_disponible_se_avisa_en_la_conversacion_sin_perder_lo_escrito", async () => {
  await montar({ frase: true, lookalike: false }, () => HttpResponse.json({ detail: "ia_no_disponible" }, { status: 503 }));

  escribirYSugerir();

  await waitFor(() => expect(conversacion().getByRole("alert")).toHaveTextContent(es.busqueda.frase.error_no_disponible));
  expect(pestana(es.busqueda.pestanas.frase)).toHaveAttribute("aria-selected", "true");  // sigue en la frase
  expect(campo(es.busqueda.frase.etiqueta)).toHaveValue(FRASE);
});

test("una_salida_ilegible_se_avisa_en_la_conversacion_sin_perder_lo_escrito", async () => {
  await montar({ frase: true, lookalike: false }, () => HttpResponse.json({ detail: "ia_salida_invalida" }, { status: 502 }));

  escribirYSugerir();

  await waitFor(() => expect(conversacion().getByRole("alert")).toHaveTextContent(es.busqueda.frase.error_interpretacion));
  expect(campo(es.busqueda.frase.etiqueta)).toHaveValue(FRASE);  // la frase no se pierde
  expect(conversacion().queryByText(FRASE)).not.toBeInTheDocument();  // y no quedó como mensaje enviado
  expect(boton(es.busqueda.frase.enviar)).toBeEnabled();  // se puede reintentar
});

test("textos_en_ingles", async () => {
  await i18n.changeLanguage("en");
  await montar();

  expect(pestana(en.busqueda.pestanas.frase)).toBeInTheDocument();
  expect(pestana(en.busqueda.pestanas.filtros)).toBeInTheDocument();
  fireEvent.click(pestana(en.busqueda.pestanas.frase)!);
  fireEvent.change(campo(en.busqueda.frase.etiqueta), { target: { value: FRASE } });
  fireEvent.click(boton(en.busqueda.frase.enviar));

  const tarjeta = await screen.findByRole("region", { name: en.busqueda.frase.voy_a_buscar });
  expect(within(screen.getByRole("log")).getByText(en.busqueda.frase.asistente)).toBeInTheDocument();
  expect(within(tarjeta).getByText("Comercio al por mayor de alimentos")).toBeInTheDocument();
  expect(boton(en.busqueda.frase.editar_en_filtros)).toBeInTheDocument();
  expect(boton(en.busqueda.frase.empezar_de_nuevo)).toBeInTheDocument();
});

test("ya_me_compran_prellena_los_filtros_y_muestra_la_explicacion", async () => {
  await montar({ frase: true, lookalike: true });
  server.use(
    http.post("*/intake/lookalike", () =>
      HttpResponse.json({
        sugerencia: { pais: "CO", ciiu: "4631", departamento: "05", ciudad: null, ingresos_min: null, palabras_clave: [], exclusiones: [] },
        explicacion: { ciiu: [["4631", 4]], departamento: [["05", 3]] },
        resueltos: 5, no_resueltos: [], costo_usd: "0.0001",
      })),
  );

  fireEvent.click(pestana(es.busqueda.pestanas.lookalike)!);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "A\nB\nC\nD\nE" } });
  fireEvent.click(screen.getAllByRole("button").find((b) => b.textContent === es.intake.lookalike.sugerir)!);

  await waitFor(() => expect(screen.queryByRole("status")).toHaveTextContent(es.busqueda.revisar_clientes));
  fireEvent.click(pestana(es.busqueda.pestanas.filtros)!);
  expect(campo("Actividad")).toHaveValue("4631");
  await waitFor(() => expect(campo("Departamento")).toHaveValue("05"));
});


// --- ajustes del QA (010-chat-ajustes) ----------------------------------------------------------------------------

const sinActividad = (extra: object = {}) => () =>
  HttpResponse.json({ sugerencia: { ...SUGERENCIA, ciiu: null, departamento: null, ciudad: null, ingresos_min: null,
    exclusiones: [] }, pregunta: null, explicacion: EXPLICACION, costo_usd: "0", ...extra });

test("la_tarjeta_siempre_muestra_pais_y_actividad_y_solo_lo_demas_si_viene", async () => {
  await montar({ frase: true, lookalike: false }, sinActividad());
  escribirYSugerir();

  const tarjeta = within(await verTarjeta());

  expect(tarjeta.getByText(es.criterios.pais)).toBeInTheDocument();
  expect(tarjeta.getByText(es.paises.CO)).toBeInTheDocument();
  expect(tarjeta.getByText(es.criterios.ciiu)).toBeInTheDocument();
  const falta = tarjeta.getByText(es.busqueda.frase.actividad_falta);
  expect(falta).toHaveClass("resumen-aviso");
  // Sin ubicación la fila de departamento aparece, pero como aviso (sin ella ninguna fuente corre).
  expect(tarjeta.getByText(es.busqueda.frase.ubicacion_falta)).toHaveClass("resumen-aviso");
  for (const clave of ["ciudad", "ingresos_min", "exclusiones"] as const) {
    expect(tarjeta.queryByText(es.criterios[clave])).not.toBeInTheDocument();
  }
  expect(tarjeta.getByText(es.criterios.palabras_clave)).toBeInTheDocument();
});

test("con_actividad_no_aparece_el_aviso_de_falta", async () => {
  await montar();
  escribirYSugerir();

  const tarjeta = within(await verTarjeta());

  expect(tarjeta.queryByText(es.busqueda.frase.actividad_falta)).not.toBeInTheDocument();
  expect(tarjeta.queryByText(es.busqueda.frase.ciiu_descartado)).not.toBeInTheDocument();
});

test("ciiu_descartado_avisa_que_la_ia_propuso_una_actividad_fuera_del_catalogo", async () => {
  await montar({ frase: true, lookalike: false }, sinActividad({ ciiu_descartado: true }));
  escribirYSugerir();

  await verTarjeta();

  expect(screen.getByText(es.busqueda.frase.ciiu_descartado)).toBeInTheDocument();
  expect(es.busqueda.frase.ciiu_descartado).toBe("La IA propuso una actividad que no está en el catálogo");
});

test("editar_en_filtros_va_en_la_misma_fila_que_vista_previa_y_buscar", async () => {
  await montar();
  escribirYSugerir();
  await verTarjeta();

  const fila = boton(es.busqueda.frase.editar_en_filtros).closest(".acciones");

  expect(fila).toHaveClass("acciones-fin");
  expect(within(fila as HTMLElement).getByRole("button", { name: es.busqueda.vista_previa })).toBeInTheDocument();
  expect(within(fila as HTMLElement).getByRole("button", { name: es.busqueda.buscar })).toBeInTheDocument();
  expect(boton(es.busqueda.frase.editar_en_filtros)).not.toHaveClass("boton-primario");
});

test("sin_actividad_deshabilita_vista_previa_y_buscar_y_editar_pasa_a_primario", async () => {
  await montar({ frase: true, lookalike: false }, sinActividad());
  escribirYSugerir();
  await verTarjeta();

  expect(boton(es.busqueda.vista_previa)).toBeDisabled();
  expect(boton(es.busqueda.buscar)).toBeDisabled();
  expect(boton(es.busqueda.frase.editar_en_filtros)).toHaveClass("boton-primario");
  expect(boton(es.busqueda.buscar)).not.toHaveClass("boton-primario");
  expect(screen.getByText(es.busqueda.frase.sin_actividad)).toHaveClass("aviso-ancho");
});

test("el_tope_por_defecto_del_chat_es_el_mismo_que_el_de_filtros", async () => {
  await montar();
  const enFiltros = (campo(es.busqueda.tope) as HTMLInputElement).value;
  escribirYSugerir();
  await verTarjeta();

  expect(enFiltros).toBe("1");
  expect((campo(es.busqueda.tope) as HTMLInputElement).value).toBe(enFiltros);
});

test("textos_nuevos_en_ingles", () => {
  expect(en.busqueda.frase.actividad_falta).toBeTruthy();
  expect(en.busqueda.frase.ciiu_descartado).toBeTruthy();
  expect(en.busqueda.frase.sin_actividad).toBeTruthy();
});

const ANCHOS: Record<string, string> = {
  "País": "campo-mitad", "Actividad": "campo-mitad", "Departamento": "campo-mitad", "Ciudad (opcional)": "campo-mitad",
  "Ingresos mínimos (USD)": "campo-mitad", "Canal preferido": "campo-mitad",
  "Palabras clave (separadas por coma)": "campo-mitad", "Exclusiones (separadas por coma)": "campo-mitad",
  "Tope de gasto (USD)": "campo-mitad", "Mensaje base": "campo-ancho",
};
const clases = () =>
  Object.fromEntries(Object.keys(ANCHOS).map((e) => [e, campo(e).closest(".campo")?.className]));

test("el_aviso_de_la_sugerencia_no_cambia_el_ancho_de_ningun_campo", async () => {
  await montar();
  await waitFor(() => expect(screen.queryByLabelText("Departamento")).toBeInTheDocument());
  const antes = clases();
  for (const [e, ancho] of Object.entries(ANCHOS)) expect(antes[e], e).toBe(`campo ${ancho}`);

  escribirYSugerir();
  await editarEnFiltros();
  await waitFor(() => expect(screen.queryByRole("status")).toHaveTextContent(es.busqueda.frase.revisar));
  expect(clases()).toEqual(antes);
});

test("despues_de_la_primera_respuesta_no_vuelve_a_preguntar_a_quien_le_vendes", async () => {
  // QA 2026-10-18: la pregunta grande encima de la tarjeta parecía que la IA no había escuchado.
  await montar();
  escribirYSugerir();
  await verTarjeta();

  expect(screen.getByText(es.busqueda.frase.etiqueta)).toHaveClass("solo-lector");  // accesible, no visible
  expect(screen.getByLabelText(es.busqueda.frase.etiqueta)).toHaveAttribute("placeholder", es.busqueda.frase.ajustar);
  expect(screen.getByLabelText(es.busqueda.frase.etiqueta)).toHaveAttribute("rows", "1");
  expect(en.busqueda.frase.ajustar).toBeTruthy();
});

test("sin_departamento_ni_ciudad_la_tarjeta_avisa_que_falta_la_ubicacion", async () => {
  // QA 2026-10-18: sin ubicación ninguna fuente corre y Buscar quedaba gris sin decir por qué.
  await montar({ frase: true, lookalike: false }, () => HttpResponse.json({
    sugerencia: { ...SUGERENCIA, departamento: null, ciudad: null }, pregunta: null, explicacion: EXPLICACION, costo_usd: "0" }));
  escribirYSugerir();

  const tarjeta = within(await verTarjeta());

  expect(tarjeta.getByText(es.busqueda.frase.ubicacion_falta)).toHaveClass("resumen-aviso");
  expect(en.busqueda.frase.ubicacion_falta).toBeTruthy();
});
