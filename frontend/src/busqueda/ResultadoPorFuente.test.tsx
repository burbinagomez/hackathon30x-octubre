import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import i18n from "../i18n";
import ResultadoPorFuente from "./ResultadoPorFuente";
import type { PorFuente } from "./tipos";

// Un caso por estado; el texto esperado está escrito a mano (no leído de los JSON) para que un cambio de copy se vea.
const CASOS: { estado: string; encontrados: number; es: string; en: string }[] = [
  { estado: "con_resultados", encontrados: 12, es: "OpenStreetMap: 12 empresas", en: "OpenStreetMap: 12 companies" },
  { estado: "con_resultados", encontrados: 1, es: "OpenStreetMap: 1 empresa", en: "OpenStreetMap: 1 company" },
  { estado: "sin_resultados", encontrados: 0, es: "OpenStreetMap: sin resultados para este filtro", en: "OpenStreetMap: no results for this filter" },
  { estado: "no_disponible", encontrados: 0, es: "OpenStreetMap: no disponible ahora", en: "OpenStreetMap: not available right now" },
  { estado: "no_soporta_criterio", encontrados: 0, es: "OpenStreetMap: no admite este criterio de búsqueda", en: "OpenStreetMap: does not support this search criterion" },
  { estado: "limite_agotado", encontrados: 0, es: "OpenStreetMap: límite de la fuente alcanzado", en: "OpenStreetMap: source limit reached" },
  { estado: "omitida_por_tope", encontrados: 0, es: "OpenStreetMap: no se consultó, pasaría el tope de gasto", en: "OpenStreetMap: not queried, it would exceed the spending cap" },
];

for (const idioma of ["es", "en"] as const) {
  test.each(CASOS)(`linea_por_estado_$estado_$encontrados_${idioma}`, async (caso) => {
    await i18n.changeLanguage(idioma);
    const por_fuente: PorFuente = { osm_overpass: { estado: caso.estado, encontrados: caso.encontrados } };

    render(<ResultadoPorFuente porFuente={por_fuente} />);

    const filas = screen.getAllByRole("listitem");
    expect(filas).toHaveLength(1);
    expect(filas[0]).toHaveTextContent(caso[idioma]);
  });
}

test("una_linea_por_fuente_en_el_orden_recibido", async () => {
  await i18n.changeLanguage("es");

  render(
    <ResultadoPorFuente
      porFuente={{
        datos_gov_co_rues: { estado: "sin_resultados", encontrados: 0 },
        osm_overpass: { estado: "con_resultados", encontrados: 12 },
        croma_supersociedades_co: { estado: "no_disponible", encontrados: 0 },
      }}
    />,
  );

  expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "RUES (datos.gov.co): sin resultados para este filtro",
    "OpenStreetMap: 12 empresas",
    "Supersociedades (Croma): no disponible ahora",
  ]);
});

test("un_estado_desconocido_se_muestra_como_no_disponible_no_como_clave_cruda", async () => {
  await i18n.changeLanguage("es");

  render(<ResultadoPorFuente porFuente={{ osm_overpass: { estado: "algo_nuevo", encontrados: 0 } }} />);

  expect(screen.getByRole("listitem")).toHaveTextContent("OpenStreetMap: no disponible ahora");
});
