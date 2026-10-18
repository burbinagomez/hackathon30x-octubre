import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import en from "../i18n/en.json";
import i18n from "../i18n";
import es from "../i18n/es.json";
import { actividades, boton, campo, manejarGeografia, respuestaVistaPrevia } from "../test/fixtures";
import { server } from "../test/servidor";
import NuevaBusqueda from "./NuevaBusqueda";

const FRASE = "vendo software contable a ferreterías medianas en Antioquia";
const SUGERENCIA = {
  pais: "CO",
  ciiu: "4631",
  departamento: "05",
  ciudad: "Medellín",
  ingresos_min: 500000000,
  palabras_clave: ["ferretería", "tornillos"],
  exclusiones: ["cadenas"],
};

type Estado = { frase: boolean; lookalike: boolean };

/** Monta Nueva búsqueda con el estado de las puertas dado. Devuelve los body que llegaron a /intake/frase y a vista-previa. */
async function montar(estado: Estado | "falla" = { frase: true, lookalike: false }, frase: () => Response | Promise<Response> = () => HttpResponse.json({ sugerencia: SUGERENCIA, costo_usd: "0.00005" })) {
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

async function escribirYSugerir(texto = FRASE) {
  fireEvent.click(pestana(es.busqueda.pestanas.frase)!);
  fireEvent.change(campo(es.busqueda.frase.etiqueta), { target: { value: texto } });
  fireEvent.click(boton(es.busqueda.frase.sugerir));
}

test("escribe_una_frase_y_prellena_el_formulario_editable", async () => {
  const { frases, vistas } = await montar();

  await escribirYSugerir();

  await waitFor(() => expect(pestana(es.busqueda.pestanas.filtros)).toHaveAttribute("aria-selected", "true"));
  expect(frases).toEqual([{ frase: FRASE }]);
  await waitFor(() => expect(campo("Departamento")).toHaveValue("05"));  // las divisiones llegan después
  expect(campo("Actividad")).toHaveValue("4631");
  expect(campo("Ciudad (opcional)")).toHaveValue("Medellín");
  expect(campo("Ingresos mínimos (USD)")).toHaveValue(500000000);
  expect(campo("Palabras clave (separadas por coma)")).toHaveValue("ferretería, tornillos");
  expect(campo("Exclusiones (separadas por coma)")).toHaveValue("cadenas");
  // Nunca llama a vista previa por sí misma, y avisa que hay que revisar.
  expect(vistas).toEqual([]);
  expect(screen.queryByRole("status")).toHaveTextContent(es.busqueda.frase.revisar);

  // Editable: el usuario pisa lo sugerido y es lo editado lo que viaja.
  fireEvent.change(campo("Palabras clave (separadas por coma)"), { target: { value: "tornillos" } });
  fireEvent.change(campo("Tope de gasto (USD)"), { target: { value: "5" } });
  fireEvent.click(boton("Vista previa"));
  await waitFor(() => expect(vistas).toHaveLength(1));
  expect(vistas[0]).toEqual({
    pais: "CO", ciiu: "4631", departamento: "05", ciudad: "Medellín", ingresos_min: 500000000,
    palabras_clave: ["tornillos"], exclusiones: ["cadenas"], canal_preferido: "email", tope_gasto_usd: 5, mensaje_base: "",
  });
});

test("una_sugerencia_con_campos_null_deja_esos_campos_vacios", async () => {
  await montar({ frase: true, lookalike: false }, () =>
    HttpResponse.json({ sugerencia: { ...SUGERENCIA, ciiu: null, departamento: null, ciudad: null, ingresos_min: null, palabras_clave: [], exclusiones: [] }, costo_usd: "0" }));

  await escribirYSugerir();

  await waitFor(() => expect(pestana(es.busqueda.pestanas.filtros)).toHaveAttribute("aria-selected", "true"));
  expect(campo("Actividad")).toHaveValue("");
  expect(campo("Ingresos mínimos (USD)")).toHaveValue(null);
  expect(campo("Palabras clave (separadas por coma)")).toHaveValue("");
});

test("la_sugerencia_no_pisa_canal_tope_ni_mensaje", async () => {
  await montar();
  fireEvent.change(campo("Tope de gasto (USD)"), { target: { value: "7" } });
  fireEvent.change(campo("Mensaje base"), { target: { value: "Hola" } });

  await escribirYSugerir();

  await waitFor(() => expect(pestana(es.busqueda.pestanas.filtros)).toHaveAttribute("aria-selected", "true"));
  expect(campo("Tope de gasto (USD)")).toHaveValue(7);
  expect(campo("Mensaje base")).toHaveValue("Hola");
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

test("el_boton_de_sugerir_exige_una_frase", async () => {
  await montar();
  fireEvent.click(pestana(es.busqueda.pestanas.frase)!);
  expect(boton(es.busqueda.frase.sugerir)).toBeDisabled();

  fireEvent.change(campo(es.busqueda.frase.etiqueta), { target: { value: "   " } });
  expect(boton(es.busqueda.frase.sugerir)).toBeDisabled();

  fireEvent.change(campo(es.busqueda.frase.etiqueta), { target: { value: FRASE } });
  expect(boton(es.busqueda.frase.sugerir)).toBeEnabled();
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

test("la_ia_no_disponible_se_avisa_y_no_toca_el_formulario", async () => {
  await montar({ frase: true, lookalike: false }, () => HttpResponse.json({ detail: "ia_no_disponible" }, { status: 503 }));

  await escribirYSugerir();

  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent(es.busqueda.frase.error_no_disponible));
  expect(pestana(es.busqueda.pestanas.frase)).toHaveAttribute("aria-selected", "true");  // sigue en la frase
});

test("una_salida_ilegible_se_avisa_con_su_texto", async () => {
  await montar({ frase: true, lookalike: false }, () => HttpResponse.json({ detail: "ia_salida_invalida" }, { status: 502 }));

  await escribirYSugerir();

  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent(es.busqueda.frase.error_interpretacion));
  expect(screen.getByLabelText(es.busqueda.frase.etiqueta)).toHaveValue(FRASE);  // la frase no se pierde
});

test("textos_en_ingles", async () => {
  await i18n.changeLanguage("en");
  await montar();

  expect(pestana(en.busqueda.pestanas.frase)).toBeInTheDocument();
  expect(pestana(en.busqueda.pestanas.filtros)).toBeInTheDocument();
  fireEvent.click(pestana(en.busqueda.pestanas.frase)!);
  fireEvent.change(campo(en.busqueda.frase.etiqueta), { target: { value: FRASE } });
  fireEvent.click(boton(en.busqueda.frase.sugerir));
  await waitFor(() => expect(screen.queryByRole("status")).toHaveTextContent(en.busqueda.frase.revisar));
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
