import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import i18n from "../i18n";
import es from "../i18n/es.json";
import { server } from "../test/servidor";
import PrimerMensaje from "./PrimerMensaje";

const ID = "11111111-1111-4111-8111-111111111111";
const C1 = "22222222-2222-4222-8222-222222222222";

test("ver el mensaje, enviar, marcar la respuesta y ver la tasa", async () => {
  let enviado = false;
  let respondio = false;
  const marcados: string[] = [];
  server.use(
    http.post("*/busquedas/:id/envio/vista-previa", () =>
      HttpResponse.json({ modo: "prueba", aprobados: 1, a_enviar: 1, asunto: "Hola", cuerpo: "Texto del mensaje" })),
    http.post("*/busquedas/:id/envio", () => { enviado = true; return HttpResponse.json({ enviados: 1 }); }),
    http.get("*/busquedas/:id/contactos", () => HttpResponse.json({ items: enviado
      ? [{ id: C1, estado: "enviado", enviado_en: "2026-10-18T12:00:00Z", respondio_en: respondio ? "2026-10-18T12:05:00Z" : null }] : [] })),
    http.post("*/contactos/:c/respondio", ({ params }) => { marcados.push(String(params.c)); respondio = true; return HttpResponse.json({ respondio: true }); }),
    http.get("*/contactos/tasa", () => HttpResponse.json({ items: enviado
      ? [{ canal: "email", contactados: 1, respondieron: respondio ? 1 : 0, tasa: respondio ? "1" : "0" }] : [] })),
  );
  await i18n.changeLanguage("es");
  render(<PrimerMensaje id={ID} />);

  expect(screen.getByRole("button", { name: es.envio.enviar })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: es.envio.ver }));
  expect(await screen.findByText("Texto del mensaje")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: es.envio.enviar }));
  fireEvent.click(await screen.findByRole("button", { name: es.envio.marcar_respondio }));

  await waitFor(() => expect(marcados).toEqual([C1]));
  expect(await screen.findByText(/1 de 1 \(100 %\)/)).toBeInTheDocument();
});

test("sin email configurado lo dice", async () => {
  server.use(
    http.post("*/busquedas/:id/envio/vista-previa", () => HttpResponse.json({ detail: "email_no_configurado" }, { status: 503 })),
    http.get("*/busquedas/:id/contactos", () => HttpResponse.json({ items: [] })),
    http.get("*/contactos/tasa", () => HttpResponse.json({ items: [] })),
  );
  await i18n.changeLanguage("es");
  render(<PrimerMensaje id={ID} />);
  fireEvent.click(screen.getByRole("button", { name: es.envio.ver }));
  expect(await screen.findByRole("alert")).toHaveTextContent(es.envio.no_configurado);
});
