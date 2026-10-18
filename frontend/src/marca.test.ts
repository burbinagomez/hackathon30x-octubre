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
const esDominioOsubdominio = (h: string, dominio: string) => h === dominio || h.endsWith(`.${dominio}`);

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

  test("no carga fuentes de Google: se sirven desde el propio sitio", () => {
    const hrefs = Array.from(leerHtml().querySelectorAll("link"), (l) => host(l.getAttribute("href")));
    expect(hrefs.filter((h) => esDominioOsubdominio(h, "googleapis.com") || esDominioOsubdominio(h, "gstatic.com"))).toEqual([]);
  });
});

describe("fuentes.css", () => {
  test("declara Poppins y DM Sans en woff2 propios con display swap", () => {
    const fuentes = import.meta.glob<string>("./fuentes.css", { query: "?raw", import: "default", eager: true });
    expect(Object.keys(fuentes)).toContain("./fuentes.css");
    const caras = fuentes["./fuentes.css"].match(/@font-face\s*\{[^}]*\}/g) ?? [];
    const de = (familia: string) =>
      caras.filter((c) => c.includes(`"${familia}"`)).map((c) => c.match(/font-weight:\s*(\d+)/)?.[1]);
    expect(de("Poppins")).toEqual(["500", "600", "700"]);
    expect(de("DM Sans")).toEqual(["400", "500", "700"]);
    // Un woff2 que falta no rompe nada visible: cae en silencio a system-ui. Por eso se cruza con public/.
    const enDisco = Object.keys(
      import.meta.glob("../public/fuentes/*.woff2", { query: "?url", import: "default", eager: true }),
    ).map((r) => r.replace("../public", ""));
    for (const c of caras) {
      expect(c).toMatch(/font-display:\s*swap/);
      const url = c.match(/url\("(\/fuentes\/[a-z0-9-]+\.woff2)"\)/)?.[1];
      expect(enDisco).toContain(url);
    }
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
