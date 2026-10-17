---
name: slice-tdd
description: Cómo se ejecuta un slice de este proyecto con TDD y Spec Kit. Cárgala antes de implementar cualquier spec. Cubre el ciclo rojo→verde→refactor en back (pytest) y front (Vitest/Playwright), qué revisa el advisor, qué va en el PR y cuándo se corta un slice.
---

# Slice con TDD

## Antes de empezar
1. Existe `specs/NNN-nombre/spec.md` con: para quién, flujo, fuera del alcance, y **"terminado cuando"** escrito como un test que hoy falla. Si no existe → `/speckit-specify` primero. No hay excepciones.
2. `/speckit-plan` produce `plan.md`: módulos tocados, puertos nuevos, migración (si hay), tests a escribir. El `advisor` lo aprueba.
3. Rama `slice/NNN-nombre` desde `main` actualizado y verde.

## Ciclo (por cada comportamiento de la spec)
1. **Rojo.** Escribe el test más pequeño que exprese el comportamiento. Nómbralo por el comportamiento, no por la función (`test_dos_leads_mismo_nit_quedan_en_uno`, no `test_dedup`). Córrelo: debe fallar por la razón correcta (no por import roto).
2. **Revisión del test.** Si el caso es de juicio (dedup, costos, cumplimiento, RLS, fórmulas), pide al `advisor` APROBADO antes de seguir.
3. **Verde.** Código mínimo. Nada "por si acaso".
4. **Refactor.** Con la suite verde. Aquí entra hexagonal: mueve a dominio/aplicación/infraestructura si quedó mezclado.
5. **Doc.** Actualiza `docs/arquitectura-backend.md` / `-frontend.md` en el mismo cambio.

## Dónde va cada test
- `backend/tests/unit/` — dominio y casos de uso con puertos falsos. Rápidos, sin DB.
- `backend/tests/integration/` — adaptadores reales contra Postgres de prueba (RLS, migraciones, costos).
- `backend/tests/arquitectura/` — `import-linter` y tests de higiene (cifrado de columnas, costos por adaptador, CLAUDE.md < 100 líneas).
- `frontend/src/**/*.test.tsx` — componentes y lógica con Testing Library.
- `frontend/e2e/` — Playwright, solo el flujo principal.
- `backend/evals/` — sets etiquetados y runner de Jev.

## Tests de caracterización
Si tocas algo que ya existe y no tiene test: primero un test que capture cómo se comporta **hoy** (aunque sea imperfecto), luego cambia. Verde antes y después.

## El PR
Contiene: tests, código, migración (si hay, separada y a mano), doc actualizada, y en la descripción: qué comportamiento añade, qué quedó fuera y por qué, comando para correrlo. Pide revisión al `security` y a un humano. **Merge solo con CI verde + 1 aprobación.** Un CI que no corre bloquea.

## Cuándo cortar
Si el slice no cabe en el tiempo asignado en `docs/prd.md` §9, se corta al último comportamiento verde y se documenta lo que falta. Un flujo completo vale más que dos a medias.
