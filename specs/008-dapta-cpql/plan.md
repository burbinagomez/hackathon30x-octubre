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
- **Storage:** una migración a mano, la **0009**. Su DDL está abajo y espera aprobación.
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

**Tarifa.** `dapta.usd_por_minuto: null` → **`TarifaPendiente`**: el import no escribe nada (spec). Para la demo hay que cargar la tarifa en `tarifas.yaml`. Ver P1.

**CPQL** (`v_cpql`), por fuente `f`:
- `costo_lista` = Σ `unidades × costo_unitario` de `costos` con `fuente = f` (incluye `gratis`);
- `costo_real` = lo mismo, sin `gratis`;
- `calificados` = leads distintos de `lead_fuentes` con `fuente = f` y `calificado = true`;
- `cpql_lista` = `costo_lista / NULLIF(calificados, 0)`, y `cpql_real` igual.

La fila `TOTAL` suma **todos** los costos del tenant, incluidos los `dapta_llamada` sin fuente, y los divide por los calificados distintos. Un divisor 0 da NULL ("sin dato"), nunca 0.

## DDL 0009 — **PENDIENTE DE APROBACIÓN DE DANIEL**

Todavía no existe en `supabase/migrations/`. Se crea como `0009_calificaciones.sql` cuando Daniel lo apruebe.

```sql
-- 0009 (008): calificaciones de Dapta y CPQL por fuente. SQL a mano. Corre como postgres (dueño).
CREATE TABLE public.calificaciones (
  tenant_id     uuid NOT NULL REFERENCES public.tenants(id),
  lead_id       uuid NOT NULL,
  calificado    boolean NOT NULL,
  calificado_en timestamptz NOT NULL,
  minutos       numeric NOT NULL CHECK (minutos BETWEEN 0 AND 60),
  importado_en  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, lead_id),
  -- Compuesta: una FK no pasa por RLS (igual que 0002).
  FOREIGN KEY (tenant_id, lead_id) REFERENCES public.leads (tenant_id, id)
);

GRANT SELECT, INSERT ON public.calificaciones TO app_rt;

ALTER TABLE public.calificaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_aislado ON public.calificaciones
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

-- security_invoker: corre como app_rt y pasa por la RLS de costos, lead_fuentes y calificaciones.
CREATE VIEW public.v_cpql WITH (security_invoker = true) AS
  WITH costo AS (
    SELECT fuente,
           sum(unidades * costo_unitario) AS costo_lista,
           sum(unidades * costo_unitario) FILTER (WHERE NOT gratis) AS costo_real
    FROM public.costos
    WHERE fuente IS NOT NULL
    GROUP BY fuente
  ), calif AS (
    SELECT lf.fuente, count(DISTINCT lf.lead_id) AS calificados
    FROM public.lead_fuentes lf
    JOIN public.calificaciones c ON c.tenant_id = lf.tenant_id AND c.lead_id = lf.lead_id
    WHERE c.calificado
    GROUP BY lf.fuente
  ), fuentes AS (
    SELECT fuente FROM costo UNION SELECT fuente FROM public.lead_fuentes
  )
  SELECT f.fuente,
         coalesce(co.costo_lista, 0) AS costo_lista,
         coalesce(co.costo_real, 0)  AS costo_real,
         coalesce(ca.calificados, 0) AS calificados,
         co.costo_lista / NULLIF(ca.calificados, 0) AS cpql_lista,
         co.costo_real  / NULLIF(ca.calificados, 0) AS cpql_real
  FROM fuentes f
  LEFT JOIN costo co USING (fuente)
  LEFT JOIN calif ca USING (fuente)
  UNION ALL
  SELECT 'TOTAL', t.costo_lista, t.costo_real, t.calificados,
         t.costo_lista / NULLIF(t.calificados, 0), t.costo_real / NULLIF(t.calificados, 0)
  FROM (
    SELECT coalesce((SELECT sum(unidades * costo_unitario) FROM public.costos), 0) AS costo_lista,
           coalesce((SELECT sum(unidades * costo_unitario) FROM public.costos WHERE NOT gratis), 0) AS costo_real,
           (SELECT count(*) FROM public.calificaciones WHERE calificado) AS calificados
  ) t;

GRANT SELECT ON public.v_cpql TO app_rt;
```

La tabla no tiene UPDATE ni DELETE porque un conflicto lo resuelve un humano. Hace falta además el espejo en `app/modelos.py` para el drift check.

## Preguntas abiertas

- **P1. Tarifa de Dapta para la demo.** `usd_por_minuto: null` [MENTORES]. Default propuesto: dejar `TarifaPendiente` como dice la spec y cargar un valor provisional en `tarifas.yaml` antes de la demo, marcado `# [MENTORES] provisional`. Lo decide Daniel.
- **P2. Costo de Dapta en el CPQL por fuente.** Pediste costo de la fuente / calificados: el `dapta_llamada` no tiene fuente, así que entra solo en `TOTAL`. El reparto en partes iguales entre las fuentes del lead (spec, Decisiones) queda fuera del mínimo. Revisión del advisor de costos.
- **P3. Moneda.** Todo `costos` está en USD hoy (`tarifas.yaml`). La vista no filtra por `moneda`. Revisión del advisor de costos.

## Fuera del mínimo (vuelve con la 006/007)

Quedan para cuando lleguen esas dos:
- el export y `v_elegibles_dapta`;
- `resultado` con cinco valores y `score`;
- la baja por `pide_no_contacto`;
- CPQL por canal;
- columnas en el tablero;
- el dataset `match_dapta`;
- el CLI `dapta pendientes`.
