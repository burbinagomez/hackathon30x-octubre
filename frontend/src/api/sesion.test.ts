import { beforeEach, expect, test } from "vitest";
import { fijarIdiomaUsuario, guardarIdiomas, type RespuestaUsuario } from "./sesion";

beforeEach(() => sessionStorage.clear());

test("fijar_idioma_usuario_no_guarda_un_valor_fuera_de_es_en", () => {
  fijarIdiomaUsuario("<script>" as never);
  expect(sessionStorage.getItem("idioma_usuario")).toBeNull();
});

test("guardar_idiomas_no_guarda_valores_fuera_de_es_en", () => {
  guardarIdiomas({ idioma_tenant: "xx", idioma_usuario: "<script>" } as unknown as RespuestaUsuario);
  expect(sessionStorage.getItem("idioma_tenant")).toBeNull();
  expect(sessionStorage.getItem("idioma_usuario")).toBeNull();
});

test("guardar_idiomas_guarda_los_validos", () => {
  guardarIdiomas({ idioma_tenant: "en", idioma_usuario: "es" });
  expect(sessionStorage.getItem("idioma_tenant")).toBe("en");
  expect(sessionStorage.getItem("idioma_usuario")).toBe("es");
});
