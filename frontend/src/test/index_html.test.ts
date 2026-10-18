import { expect, test } from "vitest";

const html = import.meta.glob<string>("../../index.html", { query: "?raw", import: "default", eager: true });

// La CSP solo permite 'self': cualquier recurso de otro origen en index.html queda bloqueado o filtra la IP.
test("no_carga_recursos_de_terceros", () => {
  expect(Object.keys(html)).toContain("../../index.html");
  const doc = new DOMParser().parseFromString(html["../../index.html"], "text/html");
  const externos = Array.from(doc.querySelectorAll("[href], [src]"), (el) =>
    el.getAttribute("href") ?? el.getAttribute("src") ?? "",
  ).filter((url) => /^(https?:)?\/\//i.test(url));
  expect(externos).toEqual([]);
});
