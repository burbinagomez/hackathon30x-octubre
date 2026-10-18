import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import i18n from "../i18n";
import en from "../i18n/en.json";
import es from "../i18n/es.json";
import { boton, campo, iniciarSesion } from "../test/fixtures";
import { server } from "../test/servidor";
import { EMPRESAS_DE_EJEMPLO } from "./ejemploLookalike";
import IntakeLookalike from "./IntakeLookalike";

const RESPUESTA = {
  sugerencia: {
    pais: "CO", ciiu: "4711", departamento: "11", ciudad: null, ingresos_min: null, palabras_clave: [], exclusiones: [],
  },
  explicacion: { ciiu: [["4711", 5], ["4752", 1]], departamento: [["11", 4], ["25", 2]] },
  resueltos: 6,
  no_resueltos: ["Droguerías Salud Plus S.A.S.", "Tiendas Mercado Fácil S.A.S."],
  costo_usd: "0.00007",
};

/** Atiende POST /intake/lookalike y devuelve los body que llegaron. */
function atender(estado = 200, cuerpo: unknown = RESPUESTA) {
  const pedidos: unknown[] = [];
  server.use(
    http.post("*/intake/lookalike", async ({ request }) => {
      pedidos.push(await request.json());
      return HttpResponse.json(cuerpo as Record<string, unknown>, { status: estado });
    }),
  );
  return pedidos;
}

const escribir = (texto: string) => fireEvent.change(campo(es.intake.lookalike.nombres), { target: { value: texto } });
const cinco = ["Uno SAS", "Dos SAS", "Tres SAS", "Cuatro SAS", "Cinco SAS"];

test("usar_ejemplo_llena_el_textarea_con_las_empresas_de_ejemplo", () => {
  iniciarSesion();
  render(<IntakeLookalike alSugerir={() => undefined} />);

  fireEvent.click(boton(es.intake.lookalike.ejemplo));

  const texto = (campo(es.intake.lookalike.nombres) as HTMLTextAreaElement).value;
  expect(texto.split("\n")).toEqual(EMPRESAS_DE_EJEMPLO);
  expect(EMPRESAS_DE_EJEMPLO.length).toBeGreaterThanOrEqual(5);
});

test("pega_nombres_y_entrega_la_sugerencia_con_su_explicacion", async () => {
  iniciarSesion();
  const pedidos = atender();
  const alSugerir = vi.fn();
  render(<IntakeLookalike alSugerir={alSugerir} />);

  escribir(`${cinco.join("\n")}\n\n  \n`);
  fireEvent.click(boton(es.intake.lookalike.sugerir));

  await waitFor(() => expect(alSugerir).toHaveBeenCalledTimes(1));
  expect(pedidos).toEqual([{ nombres: cinco }]); // una por línea, sin vacías
  expect(alSugerir).toHaveBeenCalledWith(RESPUESTA.sugerencia);
  expect(screen.queryByText("4711: 5")).toBeInTheDocument();
  expect(screen.queryByText("4752: 1")).toBeInTheDocument();
  expect(screen.queryByText("11: 4")).toBeInTheDocument();
  expect(screen.queryByText("25: 2")).toBeInTheDocument();
  expect(screen.queryByText("6 empresas encontradas")).toBeInTheDocument();
});

test("lista_los_no_resueltos", async () => {
  iniciarSesion();
  atender();
  render(<IntakeLookalike alSugerir={() => undefined} />);

  escribir(cinco.join("\n"));
  fireEvent.click(boton(es.intake.lookalike.sugerir));

  await waitFor(() => expect(screen.queryByText(es.intake.lookalike.no_resueltos)).toBeInTheDocument());
  expect(screen.queryByText("Droguerías Salud Plus S.A.S.")).toBeInTheDocument();
  expect(screen.queryByText("Tiendas Mercado Fácil S.A.S.")).toBeInTheDocument();
});

test("sin_no_resueltos_no_muestra_esa_seccion", async () => {
  iniciarSesion();
  atender(200, { ...RESPUESTA, no_resueltos: [] });
  render(<IntakeLookalike alSugerir={() => undefined} />);

  escribir(cinco.join("\n"));
  fireEvent.click(boton(es.intake.lookalike.sugerir));

  await waitFor(() => expect(screen.queryByText("6 empresas encontradas")).toBeInTheDocument());
  expect(screen.queryByText(es.intake.lookalike.no_resueltos)).not.toBeInTheDocument();
});

test.each([["a\nb\nc\nd"], [Array.from({ length: 51 }, (_, i) => `Empresa ${i}`).join("\n")]])(
  "fuera_de_5_a_50_no_pide_y_avisa",
  (texto) => {
    iniciarSesion();
    const pedidos = atender();
    const alSugerir = vi.fn();
    render(<IntakeLookalike alSugerir={alSugerir} />);

    escribir(texto);
    fireEvent.click(boton(es.intake.lookalike.sugerir));

    expect(screen.queryByRole("alert")).toHaveTextContent(es.intake.lookalike.rango);
    expect(pedidos).toEqual([]);
    expect(alSugerir).not.toHaveBeenCalled();
  },
);

test.each([
  [503, "no_disponible"],
  [422, "rango"],
  [500, "error"],
] as const)("error_%i_muestra_su_mensaje_y_no_prellena", async (estado, clave) => {
  iniciarSesion();
  atender(estado, { detail: "x" });
  const alSugerir = vi.fn();
  render(<IntakeLookalike alSugerir={alSugerir} />);

  escribir(cinco.join("\n"));
  fireEvent.click(boton(es.intake.lookalike.sugerir));

  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent(es.intake.lookalike[clave]));
  expect(alSugerir).not.toHaveBeenCalled();
});

test("los_textos_salen_en_ingles", async () => {
  iniciarSesion();
  await i18n.changeLanguage("en");
  atender();
  render(<IntakeLookalike alSugerir={() => undefined} />);

  fireEvent.change(campo(en.intake.lookalike.nombres), { target: { value: cinco.join("\n") } });
  fireEvent.click(boton(en.intake.lookalike.sugerir));

  await waitFor(() => expect(screen.queryByText("6 companies found")).toBeInTheDocument());
  expect(screen.queryByText(en.intake.lookalike.no_resueltos)).toBeInTheDocument();
});

test("los_nombres_pegados_no_se_guardan_en_el_navegador", async () => {
  iniciarSesion();
  atender();
  render(<IntakeLookalike alSugerir={() => undefined} />);

  escribir(cinco.join("\n"));
  fireEvent.click(boton(es.intake.lookalike.sugerir));
  await waitFor(() => expect(screen.queryByText("6 empresas encontradas")).toBeInTheDocument());

  const guardado = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });
  expect(guardado).not.toContain("Uno SAS");
});

test("la_explicacion_muestra_nombres_si_la_pantalla_los_conoce", async () => {
  iniciarSesion();
  atender();
  const nombres: Record<string, string> = { "4711": "Supermercados", "11": "Bogotá D.C." };
  render(
    <IntakeLookalike
      alSugerir={() => undefined}
      nombreActividad={(c) => nombres[c]}
      nombreDivision={(c) => nombres[c]}
    />,
  );

  escribir(cinco.join("\n"));
  fireEvent.click(boton(es.intake.lookalike.sugerir));

  await waitFor(() => expect(screen.queryByText("Supermercados: 5")).toBeInTheDocument());
  expect(screen.queryByText("Bogotá D.C.: 4")).toBeInTheDocument();
  expect(screen.queryByText("4752: 1")).toBeInTheDocument(); // sin nombre conocido, queda el código
});

test("una_sola_empresa_encontrada_va_en_singular", async () => {
  iniciarSesion();
  atender(200, { ...RESPUESTA, resueltos: 1 });
  render(<IntakeLookalike alSugerir={() => undefined} />);
  escribir(cinco.join("\n"));
  fireEvent.click(boton(es.intake.lookalike.sugerir));
  await waitFor(() => expect(screen.queryByText("1 empresa encontrada")).toBeInTheDocument());
});
