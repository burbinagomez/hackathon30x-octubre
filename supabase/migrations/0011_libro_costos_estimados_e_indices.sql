-- 0011: el resto del DDL de la 005 (spec:422-430) que no entró en la 0006 ni en la 0010. SQL a mano. Corre como
-- postgres (dueño). Va después de la 0010.
-- La 0006 es el DDL que aprobó el dueño y `test_migracion_0006` lo compara byte a byte, así que lo que faltaba
-- de esa tabla de la spec va acá. `revision_dedup.motivo` (spec:424) no entra: esa tabla es de la cola de dedup
-- y no existe en este repo, el ALTER fallaría. El `CHECK` de `busquedas.estado` tampoco: ya está en la 0006.

-- Lo que la vista previa guarda (spec:359-364): el estimado, la cota alta que se compara con el tope, y cuándo
-- corrió la búsqueda. Nullable: el borrador nace sin ellos, las filas que ya existen tampoco los tienen y quien
-- los escribe es `fijar_estimados` (T025/T026).
ALTER TABLE public.busquedas
  ADD COLUMN costo_estimado_usd numeric     NULL,
  ADD COLUMN costo_maximo_usd   numeric     NULL,
  ADD COLUMN ejecutada_en       timestamptz NULL;

-- El libro por lote: el costo de una búsqueda se lee por (tenant_id, lote_id) — la RLS filtra por tenant_id y el
-- lote es la búsqueda (002 migración:77). Las fuentes de un lead y el ICP se leen por (busqueda_id, fuente).
CREATE INDEX costos_tenant_lote_idx ON public.costos (tenant_id, lote_id);
CREATE INDEX lead_fuentes_busqueda_fuente_idx ON public.lead_fuentes (busqueda_id, fuente);
