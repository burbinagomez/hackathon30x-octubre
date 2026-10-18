# Spec 015 — Resultado por fuente: una fuente que falla o no encuentra no frena a las demás

**Slice:** 015 · **Rama:** `feature/015-resultado-por-fuente` · **Origen:** decisión del dueño, 2026-10-18 noche, a partir del 500 al ejecutar una búsqueda en Tolima.
**Depende de:** 005 (`EjecutarBorrador`, `_correr_fuentes`, estados de `busquedas`). Sin DDL.

> "No nos podemos frenar porque una fuente encuentre y otra no. Debemos ser claros con los usuarios." — el dueño.

## Para quién
- **La pyme usuaria:** al ejecutar una búsqueda ve, fuente por fuente, qué pasó: cuántas empresas trajo, que no encontró nada para ese ICP, que no está disponible ahora, o que no se llamó por el tope. Nunca un error genérico cuando al menos una fuente respondió.

## Qué hace
- **Aislamiento total por fuente:** cualquier excepción dentro de una fuente (no solo `LimiteFuenteAgotado`, `FuenteNoDisponible` y `CriterioNoSoportado`) queda en esa fuente; las demás siguen. Incluye lo que falle al persistir los leads de esa fuente: cada fuente corre en su propio savepoint, y si falla se deshace solo lo de esa fuente.
- **Estado por fuente** en la respuesta de `POST /busquedas/{id}/ejecutar`, con códigos (la API no devuelve texto):
  `"por_fuente": {"<clave>": {"estado": "con_resultados"|"sin_resultados"|"no_disponible"|"no_soporta_criterio"|"limite_agotado"|"omitida_por_tope", "encontrados": n}}`.
  Las fuentes no seleccionadas por país o criterio no aparecen (ya salen como descartadas en la vista previa).
- **Estado de la búsqueda:** `completada` si al menos una fuente respondió (aunque sea con cero resultados); `error` solo si todas fallaron; `tope_alcanzado` como hoy. Una fuente que falla nunca convierte la respuesta en 500.
- **Front:** después de ejecutar, una línea por fuente con su estado y conteo ("OpenStreetMap: 12 empresas", "RUES: sin resultados para este filtro", "Croma: no disponible ahora"). En es y en.
- **Diagnóstico del 500 de Tolima:** el primer paso es reproducirlo con un test y encontrar la causa raíz. Si la causa es un dato faltante (por ejemplo, la cámara de comercio de Tolima no está en `camaras_co.yaml`), la fuente responde `no_soporta_criterio` o `sin_resultados`, no un 500. Completar `camaras_co.yaml` con las 57 cámaras es la tarea 011 T054 y entra aquí solo si es la causa.

## Logs
- Se loguea la clave de la fuente y la clase de la excepción, nunca el mensaje (puede traer nombres o URLs con datos).

## Terminado cuando (tests que hoy fallan)
- `backend/tests/unit/descubrimiento/test_ejecutar_borrador.py::test_excepcion_inesperada_en_una_fuente_no_tumba_a_las_demas`: fuente A lanza `ValueError`, fuente B trae 3 empresas → estado `completada`, 3 leads guardados, `por_fuente` = A `no_disponible`, B `con_resultados` (3).
- `::test_todas_fallan_da_error_sin_500`.
- `::test_fuente_sin_empresas_es_sin_resultados_no_error`.
- `::test_falla_al_persistir_una_fuente_deshace_solo_esa` (integración, Postgres de prueba con `app_rt`).
- `::test_omitida_por_tope_y_limite_agotado_aparecen_en_por_fuente`.
- `backend/tests/integration/test_api_busquedas.py::test_ejecutar_devuelve_por_fuente` y `::test_tolima_no_da_500` (con el transporte falso que reproduzca la causa encontrada).
- `::test_log_de_fuente_caida_no_trae_el_mensaje` (`caplog`).
- Front: `frontend/src/busqueda/ResultadoPorFuente.test.tsx` con los seis estados en es y en.

## Fuera del alcance
- Guardar el estado por fuente en la base (sería DDL): se calcula al ejecutar y viaja en la respuesta.
- Reintentar automáticamente una fuente caída.
