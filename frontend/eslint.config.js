import i18next from "eslint-plugin-i18next";
import tseslint from "typescript-eslint";

export default [
  { ignores: ["dist/**", "node_modules/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { parser: tseslint.parser },
  },
  {
    // Texto visible solo vía t(...). jsx-only deja pasar rutas y claves de objeto.
    files: ["**/src/**/*.tsx"],
    ignores: ["**/src/**/*.test.tsx"],
    plugins: { i18next },
    rules: { "i18next/no-literal-string": ["error", { mode: "jsx-only" }] },
  },
];
