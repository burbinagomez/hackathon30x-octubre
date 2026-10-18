# Implementation Plan: 008 — Dapta CSV y CPQL por fuente (mínimo de demo)

**Branch**: `feature/008-dapta-cpql` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

> Este plan recorta la spec al mínimo de demo (~6 h). La spec completa depende de la 006 y la 007 (`contactos`, `v_leads_icp`, `v_costos`), que no están en `main`. Lo que queda afuera está en **Fuera del mínimo**, y vuelve cuando lleguen esas dos.
>
> Como en la 005, este slice entrega solo `plan.md` y `tasks.md`.

## Summary

La 008 mínima entrega:
- el puerto **`Calificador`** (`leer_resultados(archivo: bytes) -> list[ResultadoCalificacion | FilaRechazada]`) en un módulo nuevo, `app/modulos/calificacion`;
- el adaptador **`dapta_csv`** (ya está en `config/fuentes.yaml`, `habilitado: true`), un **`CalificadorFalso`** y la suite de contrato del puerto;
- el caso de uso **`ImportarCalificaciones`**: guarda lead → calificado sí/no con fecha y escribe `dapta_llamada` en `costos`;
- la vista **`v_cpql`**, que calcula el CPQL por fuente como costo de la fuente / leads calificados de la fuente;
- dos endpoints propios: `POST /calificaciones/importar` y `GET /calificaciones/cpql`. **El tablero no se toca**: la integración va en otro PR.

## Technical Context

- **Back:** Python 3.12, FastAPI y SQLAlchemy Core, todos ya instalados. **Sin dependencias nuevas.** El import recibe el CSV como cuerpo `text/csv` (`Request.body()`), no como multipart, para no sumar `python-multipart`.
- **Storage:** una migración a mano, `supabase/migrations/0007_calificaciones.sql` (el número es el siguiente libre en main al mergear).
- **Testing:** pytest. La integración corre contra Postgres real como `app_rt` y la valida CI. Los datos son sintéticos y no hay red.
- **Scale/Scope:** 1 módulo, 1 tabla, 1 vista, 2 endpoints, 1 adaptador.

## Constitution Check

| Principio | Qué entrega | Estado |
|---|---|---|
| I Hexagonal | `Calificador` es un Protocol en el dominio y `dapta_csv` vive en infraestructura, registrado en `fuentes.yaml`. `app.modulos.calificacion` se suma a los `containers` del contrato de capas. | OK |
| II Test primero | Rojo por aserción: esqueleto que devuelve un valor equivocado y después el verde. Cada test lleva su mutación. | OK |
| Costos (VIII) | Cada fila importada con `minutos` escribe `dapta_llamada`. La fila la escribe el caso de uso, no el adaptador: es la desviación documentada en la spec (Decisiones). | OK, desviación documentada |
| Cumplimiento | Solo se importa un lead `juridica` con fila en `cumplimiento`. Si no, es `FilaRechazada`. | OK |
| Tenant | `calificaciones` con RLS y `v_cpql` con `security_invoker`. | OK |
| Contacto | El CSV puede traer el teléfono de vuelta: las columnas no mapeadas se ignoran y `FilaRechazada` no lleva el valor. | OK |

## Diseño mínimo

**CSV de entrada** (UTF-8, con o sin BOM, ≤ 1 MB, ≤ 1000 filas). Columnas: `lead_id`, `calificado` (`si`/`no`), `fecha` (ISO 8601) y `minutos` (0–60). Los nombres son fijos en el adaptador, `# [MENTORES]` hasta ver un export real de Dapta. Las demás columnas se ignoran.

**Calificado** = `calificado = si`. Es la `demo_agendada` de la spec reducida a un booleano.

**El ref es `lead_id`.** No hay export en el mínimo, así que no existe `calificacion_id`. Un `lead_id` de otro tenant no se ve por RLS y sale como `ref_desconocida`.

**Import, por fila:**
1. `FilaRechazada(fila, motivo)` si:
   - falta una columna;
   - un valor es inválido;
   - la `fecha` es futura;
   - los `minutos` están fuera de 0–60.
2. `ref_desconocida` si el lead no existe para el tenant.
3. `no_cumple` si el lead no es `juridica` o no tiene fila en `cumplimiento`.
4. En una sola transacción:
   - INSERT en `calificaciones`;
   - si entró, INSERT `dapta_llamada` con `unidades = minutos`, `costo_unitario = tarifa`, `lead_id`, `fuente = NULL`, `canal = NULL`, `ts = fecha`.
5. Si el lead ya estaba: con el mismo `calificado` es `duplicada` (no-op); con otro es `conflicto`, que no cambia nada.

**Tarifa.** `dapta.usd_por_minuto: 0.333` (docs.dapta.ai, "Billing and credits": 1.000 créditos = US$1; aprobado por Daniel, 2026-10-18) — minuto **contestado**, redondeado hacia arriba al minuto entero: `costo = ceil(minutos) * Decimal("0.333")`. Si la tarifa falta (`null`) → **`TarifaPendiente`**: el import no escribe nada. Ver P1.

El CSV del mínimo (`lead_id, calificado, fecha, minutos`) no distingue el resultado de la llamada: buzón de voz (0.075 USD por llamada) y no contestada (0.045 USD por llamada) son tarifas reales de Dapta pero no se implementan ahora porque no hay columna que las identifique. Quedan pendientes para cuando el CSV traiga esa columna (spec completa, fuera del mínimo — ver "Fuera del mínimo").

**CPQL** (`v_cpql`), por fuente `f`:
- `costo_lista` = Σ `unidades × costo_unitario` de `costos` con `fuente = f` (incluye `gratis`);
- `costo_real` = lo mismo, sin `gratis`;
- `calificados` = leads distintos de `lead_fuentes` con `fuente = f` y `calificado = true`;
- `cpql_lista` = `costo_lista / NULLIF(calificados, 0)`, y `cpql_real` igual.

Un costo sin fuente (el `dapta_llamada`) va a la fila **`sin_atribuir`**, como en el tablero: tiene costo pero no CPQL (0 calificados → NULL). Σ costo de las filas (sin `TOTAL`) = Σ `costos` del tenant sin evals: ningún costo desaparece del CPQL.

La fila `TOTAL` suma **todos** los costos del tenant y los divide por los calificados distintos. Un divisor 0 da NULL ("sin dato"), nunca 0.

## DDL 0007 — aprobado por Daniel (2026-10-18)

Está en `supabase/migrations/0007_calificaciones.sql`. Lo aprobó con tres cambios:
1. el número es el siguiente libre en main y se renombra si al mergear ya entró otro;
2. `REVOKE ALL` a `anon` y `authenticated` sobre `calificaciones` y `v_cpql`, en un bloque `DO` como el de la 0006, con test de privilegios;
3. la FK compuesta va a `leads (tenant_id, id)`, que existe como UNIQUE desde la 0002.

Además, `v_cpql` se alineó al criterio de costos del tablero (#49):
- los costos con `fuente = 'evals'` no entran;
- un costo sin dato queda NULL y no se convierte en 0;
- un tenant sin datos no tiene fila `TOTAL`.

La tabla no tiene UPDATE ni DELETE porque un conflicto lo resuelve un humano. El espejo está en `app/modelos.py`.

## Preguntas abiertas

- **P1. Tarifa de Dapta para la demo.** Resuelta: Daniel dio el valor real, `0.333` USD/min contestado (docs.dapta.ai), ya cargado en `tarifas.yaml`. Buzón de voz y no contestada quedan pendientes (ver sección "Tarifa").
- **P2. Costo de Dapta en el CPQL por fuente.** Resuelta (Daniel, 2026-10-18): el CPQL por fuente no incluye Dapta; el `dapta_llamada` va a la fila `sin_atribuir`, a la vista, y entra en `TOTAL`. El reparto en partes iguales entre las fuentes del lead (spec, Decisiones) queda fuera del mínimo.
- **P3. Moneda.** Todo `costos` está en USD hoy (`tarifas.yaml`). La vista no filtra por `moneda`. Revisión del advisor de costos.

## Fuera del mínimo (vuelve con la 006/007)

Quedan para cuando lleguen esas dos:
- el export y `v_elegibles_dapta`;
- tarifas de buzón de voz (0.075 USD por llamada) y no contestada (0.045 USD por llamada), cuando el CSV traiga una columna de resultado de la llamada;
- `resultado` con cinco valores y `score`;
- la baja por `pide_no_contacto`;
- CPQL por canal;
- columnas en el tablero;
- el dataset `match_dapta`;
- el CLI `dapta pendientes`.
