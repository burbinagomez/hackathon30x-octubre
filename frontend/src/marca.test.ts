import { describe, expect, test } from "vitest";

// Por glob y no por import estático: si el archivo falta, el rojo lo da una aserción, no la resolución.
const tokens = import.meta.glob<string>("./tokens.css", {
  query: "?raw",
  import: "default",
  eager: true,
});
const html = import.meta.glob<string>("../index.html", {
  query: "?raw",
  import: "default",
  eager: true,
});

function leerTokens(): string {
  expect(Object.keys(tokens)).toContain("./tokens.css");
  return tokens["./tokens.css"];
}

function leerHtml(): Document {
  expect(Object.keys(html)).toContain("../index.html");
  return new DOMParser().parseFromString(html["../index.html"], "text/html");
}

describe("tokens.css", () => {
  test("define en :root las seis variables de marca", () => {
    const root = leerTokens().match(/:root\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(root).toMatch(/--color-acento:\s*#cbe850\s*;/i);
    expect(root).toMatch(/--color-oscuro:\s*#1a1a1c\s*;/i);
    expect(root).toMatch(/--color-fondo:\s*#ffffff\s*;/i);
    expect(root).toMatch(/--color-gris:\s*#9b9999\s*;/i);
    expect(root).toMatch(/--fuente-titulos:[^;]*Poppins/);
    expect(root).toMatch(/--fuente-texto:[^;]*DM Sans/);
  });

  test("h1–h6 usan var(--fuente-titulos)", () => {
    expect(leerTokens()).toMatch(
      /h1\s*,\s*h2\s*,\s*h3\s*,\s*h4\s*,\s*h5\s*,\s*h6\s*\{[^}]*font-family:\s*var\(--fuente-titulos\)/,
    );
  });
});

describe("tema oscuro", () => {
  const bloqueOscuro = () => {
    const m = leerTokens().match(
      /@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{([^}]*)\}/,
    );
    expect(m, "falta @media (prefers-color-scheme: dark) con :root").not.toBeNull();
    return m![1];
  };

  test("define --color-blanco y los tokens semánticos del tema claro en :root", () => {
    const root = leerTokens().match(/:root\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(root).toMatch(/--color-blanco:\s*#ffffff\s*;/i);
    for (const t of ["superficie", "texto", "borde", "acento-texto"]) {
      expect(root, t).toMatch(new RegExp(`--color-${t}:`));
    }
    expect(root).toMatch(/color-scheme:\s*light dark\s*;/);
  });

  test("el bloque oscuro redefine fondo (#1A1A1C) y texto (#FFFFFF)", () => {
    const oscuro = bloqueOscuro();
    expect(oscuro).toMatch(/--color-superficie:\s*var\(--color-oscuro\)\s*;/);
    expect(oscuro).toMatch(/--color-texto:\s*var\(--color-blanco\)\s*;/);
    expect(oscuro).toMatch(/--color-acento-texto:\s*var\(--color-acento\)\s*;/);
  });

  test("body usa los tokens semánticos", () => {
    const body = leerTokens().match(/\bbody\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(body).toMatch(/background:\s*var\(--color-superficie\)/);
    expect(body).toMatch(/color:\s*var\(--color-texto\)/);
  });

  test("index.html declara meta color-scheme light dark", () => {
    const meta = leerHtml().querySelector('meta[name="color-scheme"]');
    expect(meta?.getAttribute("content")).toBe("light dark");
  });
});

// Compara el hostname parseado: un `includes` sobre la URL aceptaría cualquier host que lo contenga.
const host = (href: string | null) => {
  try {
    return new URL(href ?? "").hostname;
  } catch {
    return "";
  }
};

describe("index.html", () => {
  test("tiene el meta viewport", () => {
    const meta = leerHtml().querySelector('meta[name="viewport"]');
    expect(meta?.getAttribute("content")).toBe("width=device-width, initial-scale=1");
  });

  test("carga Poppins y DM Sans de Google Fonts con preconnect y display=swap", () => {
    const doc = leerHtml();
    const preconnect = Array.from(doc.querySelectorAll('link[rel="preconnect"]'), (l) =>
      l.getAttribute("href"),
    );
    expect(preconnect.some((h) => host(h) === "fonts.googleapis.com")).toBe(true);
    expect(preconnect.some((h) => host(h) === "fonts.gstatic.com")).toBe(true);

    const hojas = Array.from(doc.querySelectorAll('link[rel="stylesheet"]'), (l) =>
      l.getAttribute("href") ?? "",
    ).filter((h) => host(h) === "fonts.googleapis.com");
    expect(hojas.some((h) => h.includes("family=Poppins"))).toBe(true);
    expect(hojas.some((h) => h.includes("family=DM+Sans"))).toBe(true);
    expect(hojas.every((h) => h.includes("display=swap"))).toBe(true);
  });
});

test("ningún archivo fuera de tokens.css escribe los hex de marca", () => {
  const archivos = import.meta.glob<string>(
    ["./**/*.{ts,tsx,css}", "!./tokens.css", "!./marca.test.ts"],
    { query: "?raw", import: "default", eager: true },
  );
  // Sin esto, un glob vacío o un CSS vaciado por vitest harían pasar la negativa.
  expect(Object.keys(archivos)).toContain("./App.tsx");
  expect(archivos["./main.tsx"]).toMatch(/import\s+["']\.\/tokens\.css["']/);
  for (const [ruta, contenido] of Object.entries(archivos)) {
    expect(typeof contenido, ruta).toBe("string");
    expect(contenido.length, ruta).toBeGreaterThan(0);
  }

  const conHex = Object.keys(archivos).filter((ruta) =>
    /#(cbe850|1a1a1c|fff(fff)?|9b9999)\b/i.test(archivos[ruta]),
  );
  expect(conHex).toEqual([]);
});
