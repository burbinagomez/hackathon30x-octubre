import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, expect, test } from "vitest";
import i18n from "../i18n";
import en from "../i18n/en.json";
import es from "../i18n/es.json";
import { server } from "../test/servidor";
import LeadsDeBusqueda from "./LeadsDeBusqueda";
import type { LeadListado } from "./tipos";

const ID = "11111111-1111-4111-8111-111111111111";
const OSM = { fuente: "osm_overpass", texto: "© OpenStreetMap contributors", url: "https://www.openstreetmap.org/copyright" };
const lead = (n: number, extra: Partial<LeadListado> = {}): LeadListado => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`, nombre: `Empresa ${n} SAS`, tipo_titular: "juridica",
  fuentes: ["osm_overpass"], licencias: ["ODbL 1.0"], ciudad: "Bogotá", tiene_web: true, tiene_telefono: null,
  tiene_email: null, ...extra,
});
const pagina = (items: LeadListado[], extra = {}) => ({
  items, total: items.length, pagina: 1, tamano: 25, atribuciones: [OSM], ...extra,
});

const sinTrabajo = { en_curso: false, procesados: 0, contactables: 0, pendientes: 0, total: 0, error: null };
beforeEach(() => {
  server.use(
    http.post("*/busquedas/:id/enriquecer", () => HttpResponse.json(sinTrabajo, { status: 202 })),
    http.get("*/busquedas/:id/enriquecimiento", () => HttpResponse.json(sinTrabajo)),
  );
});

async function montar(respuesta: ReturnType<typeof pagina>, idioma = "es") {
  server.use(http.get("*/busquedas/:id/leads", () => HttpResponse.json(respuesta)));
  await i18n.changeLanguage(idioma);
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByRole("table")).toBeInTheDocument());
}

test("la juridica sale por su nombre y la natural como persona protegida", async () => {
  await montar(pagina([lead(1), lead(2, { nombre: null, tipo_titular: "natural", tiene_web: false })]));
  expect(screen.queryByText("Empresa 1 SAS")).toBeInTheDocument();
  expect(screen.queryByText("Persona natural (datos protegidos)")).toBeInTheDocument();
});

test("natural en ingles", async () => {
  await montar(pagina([lead(2, { nombre: null, tipo_titular: "natural" })]), "en");
  expect(screen.queryByText(en.leads.natural_protegida)).toBeInTheDocument();
  expect(en.leads.natural_protegida).not.toBe(es.leads.natural_protegida);
});

test("muestra fuentes, ciudad, licencia y web, y no pinta columnas de contacto sin dato", async () => {
  await montar(pagina([lead(1)]));
  const fila = screen.getAllByRole("row")[1];
  expect(fila).toHaveTextContent("OpenStreetMap");
  expect(fila).toHaveTextContent("Bogotá");
  expect(fila).toHaveTextContent("ODbL 1.0");
  const encabezados = screen.getAllByRole("columnheader").map((h) => h.textContent);
  expect(encabezados).not.toContain("Teléfono");
  expect(encabezados).not.toContain("Correo");
  expect(encabezados).toContain("Sitio web");
});

test("muestra el telefono, el correo y la web de la juridica como enlaces", async () => {
  // Daniel, 2026-10-18: "esto me debería mostrar los datos de los contactos, no mostrarme la palabra sí".
  await montar(pagina([lead(1, { tiene_telefono: true, tiene_email: false, tiene_web: true,
    telefono: "+57 601 555 0101", email: null, web: "https://lumea.example" })]));
  const encabezados = screen.getAllByRole("columnheader").map((h) => h.textContent);
  expect(encabezados).toContain("Teléfono");
  expect(encabezados).toContain("Correo");
  const celdas = within(screen.getAllByRole("row")[1]).getAllByRole("cell");
  const de = (etiqueta: string) => celdas.find((c) => c.getAttribute("data-etiqueta") === etiqueta)!;
  expect(within(de("Teléfono")).getByRole("link", { name: "+57 601 555 0101" })).toHaveAttribute("href", "tel:+576015550101");
  expect(de("Correo").textContent).toBe("—");
  expect(within(de("Sitio web")).getByRole("link", { name: "lumea.example" })).toHaveAttribute("href", "https://lumea.example");
});

test("un correo se muestra como mailto", async () => {
  await montar(pagina([lead(1, { tiene_email: true, email: "hola@lumea.example" })]));
  expect(screen.getByRole("link", { name: "hola@lumea.example" })).toHaveAttribute("href", "mailto:hola@lumea.example");
});

test("la natural (contacto null) no pinta Si ni guion en contacto", async () => {
  await montar(pagina([lead(1, { tiene_telefono: true, tiene_email: true }), lead(2, { nombre: null, tipo_titular: "natural" })]));
  const celdas = within(screen.getAllByRole("row")[2]).getAllByRole("cell");
  expect(celdas.find((c) => c.getAttribute("data-etiqueta") === "Teléfono")?.textContent).toBe("");
});

test("el checkbox Solo con contacto agrega con_contacto=true, vuelve a la pagina 1 y se quita", async () => {
  const pedidas: string[] = [];
  server.use(http.get("*/busquedas/:id/leads", ({ request }) => {
    pedidas.push(new URL(request.url).search);
    return HttpResponse.json(pagina([lead(1, { tiene_telefono: true, tiene_email: true })], { total: 30 }));
  }));
  await i18n.changeLanguage("es");
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByRole("table")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
  await waitFor(() => expect(pedidas).toHaveLength(2));

  const caja = screen.getByRole("checkbox", { name: "Solo con contacto" });
  expect(caja).not.toBeChecked();
  fireEvent.click(caja);

  await waitFor(() => expect(pedidas).toHaveLength(3));
  expect(pedidas).toEqual(["?pagina=1&tamano=25", "?pagina=2&tamano=25", "?pagina=1&tamano=25&con_contacto=true"]);
  expect(screen.getByRole("checkbox", { name: "Solo con contacto" })).toBeChecked();
  fireEvent.click(screen.getByRole("checkbox", { name: "Solo con contacto" }));
  await waitFor(() => expect(pedidas).toHaveLength(4));
  expect(pedidas[3]).toBe("?pagina=1&tamano=25");
});

test("con el filtro y sin resultados el checkbox sigue para quitarlo, y en ingles", async () => {
  server.use(http.get("*/busquedas/:id/leads", ({ request }) =>
    HttpResponse.json(pagina([], { total: 0 }), { headers: { "x-q": new URL(request.url).search } })));
  await i18n.changeLanguage("en");
  render(<LeadsDeBusqueda id={ID} />);
  const caja = await screen.findByRole("checkbox", { name: en.leads.solo_con_contacto });
  expect(en.leads.solo_con_contacto).not.toBe(es.leads.solo_con_contacto);
  fireEvent.click(caja);
  await waitFor(() => expect(screen.getByRole("checkbox", { name: en.leads.solo_con_contacto })).toBeChecked());
  expect(screen.getByText(en.leads.sin_leads)).toBeInTheDocument();
  await i18n.changeLanguage("es");
});

test("pagina: pide la siguiente con tamano 25 y deshabilita Anterior en la primera", async () => {
  const pedidas: string[] = [];
  server.use(
    http.get("*/busquedas/:id/leads", ({ request }) => {
      const u = new URL(request.url);
      pedidas.push(`${u.searchParams.get("pagina")}/${u.searchParams.get("tamano")}`);
      const p = Number(u.searchParams.get("pagina"));
      return HttpResponse.json(pagina([lead(p)], { total: 30, pagina: p }));
    }),
  );
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByText("Empresa 1 SAS")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
  expect(screen.queryByText("Página 1 de 2")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));

  await waitFor(() => expect(screen.queryByText("Empresa 2 SAS")).toBeInTheDocument());
  expect(pedidas).toEqual(["1/25", "2/25"]);
  expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
});

test("las atribuciones de la API van al pie con su enlace", async () => {
  await montar(pagina([lead(1)]));
  expect(screen.getByRole("link", { name: OSM.texto })).toHaveAttribute("href", OSM.url);
});

test("sin atribuciones no hay pie", async () => {
  await montar(pagina([lead(1)], { atribuciones: [] }));
  expect(screen.queryByLabelText("Atribución de datos")).not.toBeInTheDocument();
});

test("busqueda sin leads", async () => {
  server.use(http.get("*/busquedas/:id/leads", () => HttpResponse.json(pagina([], { total: 0 }))));
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByText("Esta búsqueda no trajo leads.")).toBeInTheDocument());
});

test("404 muestra no encontrada", async () => {
  server.use(http.get("*/busquedas/:id/leads", () => HttpResponse.json({ detail: "no_encontrada" }, { status: 404 })));
  render(<LeadsDeBusqueda id={ID} />);
  await waitFor(() => expect(screen.queryByRole("alert")).toHaveTextContent("No se encontró la búsqueda."));
});

const estado = (extra = {}) => ({ en_curso: false, procesados: 0, contactables: 0, pendientes: 0, total: 0, error: null, ...extra });

test("no hay boton de buscar telefono y email: la busqueda de contactos es automatica", async () => {
  await montar(pagina([lead(1)]));
  expect(screen.queryByRole("button", { name: /Buscar teléfono y email/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Seguir con los que quedan/ })).not.toBeInTheDocument();
});

test("al montar hace POST una vez y consulta el avance hasta que termina, recargando la lista", async () => {
  let posts = 0;
  let gets = 0;
  let listas = 0;
  server.use(
    http.get("*/busquedas/:id/leads", () => { listas += 1; return HttpResponse.json(pagina([lead(1)])); }),
    http.post("*/busquedas/:id/enriquecer", () => {
      posts += 1;
      return HttpResponse.json(estado({ en_curso: true, procesados: 0, pendientes: 4, total: 4 }), { status: 202 });
    }),
    http.get("*/busquedas/:id/enriquecimiento", () => {
      gets += 1;
      return HttpResponse.json(gets === 1
        ? estado({ en_curso: true, procesados: 2, pendientes: 2, total: 4, contactables: 1 })
        : estado({ procesados: 4, pendientes: 0, total: 4, contactables: 3 }));
    }),
  );
  await i18n.changeLanguage("es");
  render(<LeadsDeBusqueda id={ID} cadaMs={20} />);

  expect(await screen.findByText("Buscando contactos… 0 de 4")).toBeInTheDocument();
  expect(await screen.findByText("Buscando contactos… 2 de 4")).toBeInTheDocument();
  expect(await screen.findByText("3 con contacto")).toBeInTheDocument();
  expect(posts).toBe(1);
  expect(gets).toBe(2);
  await waitFor(() => expect(listas).toBeGreaterThanOrEqual(3)); // cada cambio de procesados recarga la lista
  expect(screen.queryByText(/Buscando contactos/)).not.toBeInTheDocument();
});

test("si hubo error muestra el aviso chico con Reintentar, que vuelve a arrancar", async () => {
  let posts = 0;
  server.use(
    http.get("*/busquedas/:id/leads", () => HttpResponse.json(pagina([lead(1)]))),
    http.post("*/busquedas/:id/enriquecer", () => {
      posts += 1;
      return HttpResponse.json(posts === 1 ? estado({ error: "error_tanda", pendientes: 3, total: 4, procesados: 1 })
        : estado({ en_curso: true, procesados: 1, pendientes: 3, total: 4 }), { status: 202 });
    }),
    http.get("*/busquedas/:id/enriquecimiento", () => HttpResponse.json(estado({ en_curso: true, procesados: 1, pendientes: 3, total: 4 }))),
  );
  await i18n.changeLanguage("es");
  render(<LeadsDeBusqueda id={ID} cadaMs={20} />);

  expect(await screen.findByText(es.enriquecer.error)).toBeInTheDocument();
  const reintentar = screen.getByRole("button", { name: es.enriquecer.reintentar });
  expect(reintentar).not.toHaveClass("boton-primario");
  fireEvent.click(reintentar);

  expect(await screen.findByText("Buscando contactos… 1 de 4")).toBeInTheDocument();
  expect(posts).toBe(2);
  expect(screen.queryByText(es.enriquecer.error)).not.toBeInTheDocument();
});

test("la fila de herramientas tiene el conteo y el checkbox", async () => {
  await montar(pagina([lead(1)], { total: 12 }));
  const fila = document.querySelector(".lista-herramientas") as HTMLElement;
  expect(fila).not.toBeNull();
  expect(within(fila).getByText(/12 leads/)).toBeInTheDocument();
  expect(within(fila).getByRole("checkbox", { name: "Solo con contacto" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox").closest("label")).toHaveClass("filtro-contacto"); // el label envuelve al input
});

test("el progreso sale en ingles", async () => {
  server.use(
    http.get("*/busquedas/:id/leads", () => HttpResponse.json(pagina([lead(1)]))),
    http.post("*/busquedas/:id/enriquecer", () =>
      HttpResponse.json(estado({ en_curso: true, procesados: 1, pendientes: 1, total: 2 }), { status: 202 })),
    http.get("*/busquedas/:id/enriquecimiento", () =>
      HttpResponse.json(estado({ procesados: 2, total: 2, contactables: 1 }))),
  );
  await i18n.changeLanguage("en");
  render(<LeadsDeBusqueda id={ID} cadaMs={20} />);
  expect(await screen.findByText("Finding contacts… 1 of 2")).toBeInTheDocument();
  expect(await screen.findByText("1 with contact")).toBeInTheDocument();
  expect(en.enriquecer.buscando).not.toBe(es.enriquecer.buscando);
  await i18n.changeLanguage("es");
});
