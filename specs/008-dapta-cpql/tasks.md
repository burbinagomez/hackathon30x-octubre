# Tasks: 008 — Dapta CSV y CPQL por fuente (mínimo de demo)

**Input**: [plan.md](./plan.md), [spec.md](./spec.md)

Formato: `- [ ] TNNN [MIN] [P?] [Paso n] descripción`. Rojo por aserción: antes de cada rojo va un esqueleto que devuelve un valor equivocado, para que el test falle por `assert` y no por `ImportError`. Cada test lleva su **Mutación**, el sabotaje con nombre que lo tiene que poner rojo. Las marcas (advisor) y (security) indican quién revisa.

Los tests de integración necesitan `TEST_DATABASE_URL`. No hay Postgres local: los corre CI.

## Fase 0 — DDL (PARADA)

- [ ] T001 [MIN] [Paso 0] Aprobación de Daniel del DDL 0009 (plan.md). **No se crea ningún archivo en `supabase/migrations/` antes.**
- [ ] T002 [MIN] [Paso 0] Tests rojos de migración:
  - `tests/arquitectura/test_migraciones.py` cubre la 0009;
  - `tests/integration/test_rls.py` suma `calificaciones` a `TABLAS` y `v_cpql` a `VISTAS`.
  - **Mutación `rls_calificaciones_apagada`**: sin `ENABLE ROW LEVEL SECURITY`, tenant B lee la calificación de A.
  - **Mutación `v_cpql_sin_security_invoker`**: la vista corre como dueño y B ve el CPQL de A.
- [ ] T003 [MIN] [Paso 0] `supabase/migrations/0009_calificaciones.sql` y el espejo en `app/modelos.py`. Verde de T002 y del drift check.

## Fase 1 — Puerto y adaptador

- [ ] T004 [MIN] [Paso 1] Dominio `app/modulos/calificacion/dominio/`:
  - `ResultadoCalificacion(lead_id, calificado, fecha, minutos)`;
  - `FilaRechazada(fila, motivo)`, **sin el valor**;
  - el Protocol `Calificador`.
  - Suma `app.modulos.calificacion` a `containers` en `pyproject.toml`.
- [ ] T005 [MIN] [Paso 1] (advisor) Suite de contrato `tests/contratos/test_calificador.py`, parametrizada sobre `DaptaCSV` y `CalificadorFalso`:
  - `::test_leer_resultados_mapea_si_no_fecha_minutos`;
  - `::test_valor_desconocido_es_fila_rechazada_no_excepcion`;
  - `::test_columnas_no_mapeadas_se_ignoran`;
  - `::test_archivo_sobre_limite_es_entrada_invalida`.
  - **Mutación `rechazo_lleva_valor`**: `FilaRechazada` incluye el valor. El test pone `+573001112233` en `calificado` y asierta que no aparece en `repr` de la salida.
- [ ] T006 [MIN] [Paso 1] Esqueleto de `infraestructura/dapta_csv.py` que devuelve `[]` → rojo por aserción → verde. `csv` de stdlib, `utf-8-sig`, `fecha` futura y `minutos` fuera de 0–60 son `FilaRechazada`.
- [ ] T007 [MIN] [P] [Paso 1] `tests/arquitectura/test_costos_por_adaptador.py`: `DaptaCSV` queda afuera **a propósito**, con comentario: no hace operación de salida, la llamada la hace Dapta (spec).

## Fase 2 — Import (costos, cumplimiento, tenant)

- [ ] T008 [MIN] [Paso 2] (advisor) Tests unitarios de `aplicacion/importar_calificaciones.py` con un repo falso y `RegistroCostos` falso:
  - `::test_calificado_escribe_dapta_llamada_con_minutos_y_tarifa`, que asierta `Decimal("…")` y `type is Decimal`;
  - `::test_tarifa_null_es_tarifa_pendiente_y_no_escribe_nada`;
  - `::test_duplicada_no_escribe_costo_de_nuevo`;
  - `::test_conflicto_no_cambia_nada`;
  - `::test_ts_del_costo_es_la_fecha_de_la_llamada`.
  - **Mutación `import_sin_costo`**: guarda la calificación y no escribe `dapta_llamada`.
  - **Mutación `costo_en_duplicada`**: el reimport escribe el costo dos veces.
  - **Mutación `tarifa_null_como_cero`**: con la tarifa en `null` escribe `costo_unitario = 0`.
- [ ] T009 [MIN] [Paso 2] Esqueleto de caso de uso que no escribe nada → rojo por aserción → verde.
- [ ] T010 [MIN] [Paso 2] (security) Integración `tests/integration/test_calificaciones_repo.py`:
  - `::test_lead_natural_es_no_cumple` y `::test_lead_sin_cumplimiento_es_no_cumple`;
  - `::test_lead_de_otro_tenant_es_ref_desconocida`;
  - `::test_calificacion_y_costo_en_la_misma_transaccion`: si el INSERT de costos falla, no queda la calificación.
  - **Mutación `importa_persona_natural`**: se saca el filtro `tipo_titular = 'juridica'`.
  - **Mutación `importa_sin_cumplimiento`**: se saca el JOIN a `cumplimiento`.
  - **Mutación `ref_cruza_tenant`**: el repo lee leads con el engine admin y B califica un lead de A.
- [ ] T011 [MIN] [Paso 2] `infraestructura/postgres_calificaciones.py`: calificación y `dapta_llamada` en una `unidad_de_trabajo`. Verde de T010.
- [ ] T012 [MIN] [Paso 2] `composicion.py`: `cargar_tarifas()` suma `dapta`, con `null` como `None` y nunca como 0.

## Fase 3 — CPQL y endpoints

- [ ] T013 [MIN] [Paso 3] (advisor) Integración `tests/integration/test_cpql.py`. Fixture sintético calculado a mano:
  - 2 fuentes (`osm_overpass` y `datos_gov_co_rues`);
  - 1 lead en las dos fuentes;
  - costos con y sin `gratis`;
  - 1 `dapta_llamada`.
  - `::test_cpql_por_fuente_es_costo_de_la_fuente_sobre_calificados`;
  - `::test_sin_calificados_cpql_es_null_no_cero`;
  - `::test_total_incluye_dapta_y_cuenta_leads_distintos`.
  - **Mutación `cpql_divide_por_todos_los_leads`**: el divisor cuenta los leads sin `calificado = true`.
  - **Mutación `total_sin_dapta`**: TOTAL filtra `fuente IS NOT NULL`.
- [ ] T014 [MIN] [Paso 3] Repo de lectura `infraestructura/persistencia/repositorio_cpql.py` sobre `v_cpql` (patrón de `repositorio_tablero.py`, **sin tocarlo**).
- [ ] T015 [MIN] [Paso 3] (security) `tests/integration/test_api_calificaciones.py`:
  - `POST /calificaciones/importar` (cuerpo `text/csv`, ≤ 1 MB) y `GET /calificaciones/cpql`, ambos con `Depends(tenant_actual)`;
  - montos serializados como string y la API devuelve códigos de motivo, no texto;
  - sin sesión da 401.
  - **Mutación `endpoint_sin_sesion`**: se saca el `Depends`.
- [ ] T016 [MIN] [Paso 3] `app/api/calificaciones.py` registrado en la app. Verde de T015.

## PARADAS

1. T001: DDL para aprobar.
2. Después de T013: revisión del advisor de costos sobre T008, T013 y P2/P3.
3. Al terminar: diff completo, sin push.
