# Implementation Plan: 011 — datos.gov.co (`c82u-588k`), segunda fuente de descubrimiento, con contrato

**Branch**: `feature/011-datos-gov-co` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)
**Input**: `specs/011-datos-gov-co/spec.md`

> Formato de `/speckit-plan` aplicado a mano: `setup-plan.sh` no resuelve el feature. No hay `research.md`, `data-model.md` ni `contracts/`, porque la spec ya fija las consultas SoQL medidas, el mapeo y el esquema. Repetirlos acá crearía dos fuentes de verdad.

## Summary

Este slice suma un tercer adaptador de `FuenteDescubrimiento`, `datos_gov_co_rues`, que lee el registro mercantil de Confecámaras en datos.gov.co (dataset SODA `c82u-588k`) filtrando por CIIU y departamento.
- **Personas naturales.** La persona natural se excluye en el servidor (`organizacion_juridica != 'PERSONA NATURAL'`) y el cliente descarta de nuevo lo que no debió llegar. Las naturales no se descargan: se cuentan con un `count(*)` aparte y el número queda en `busquedas.naturales_por_fuente`.
- **Costos.** Cada intento HTTP escribe `socrata_descarga` en `costos`.
- **Cumplimiento.** Cada lead nuevo lleva su fila en `cumplimiento` con `CC-BY-SA-4.0`.
- **Registro.** El YAML real pasa a `habilitado: true` en el mismo commit en que el adaptador pasa la suite de contrato. La demo de desconexión usa un YAML temporal vía `FUENTES_YAML`.
- **Tests sin red.** Una fixture `autouse` bloquea toda conexión que no sea a loopback en `unit/` y `contratos/`.

## Technical Context

**Language/Version**: Python 3.12. Sin front: la columna del tablero se movió a la 005 (D7).
**Primary Dependencies**:
- `httpx`, que ya está.
- `pyyaml`, que lo agrega la 002 (T001) en `dependencies`. La 011 **no** lo vuelve a declarar.
- No se suma ninguna dependencia nueva: la fixture sin red es stdlib, sin `pytest-socket`.

**Storage**: Postgres (Supabase). La 011 trae una migración nueva con la columna `busquedas.naturales_por_fuente`. Reutiliza `fuente_cache` (002) y `costos` (002) sin cambiarles el esquema.
**Testing**: `pytest` (unit, contratos, integration). Sin Vitest (D7) y sin Playwright: el E2E de búsqueda lo cortó la 005.
**Target Platform**: servicio `api` en Railway, más la CLI local.
**Project Type**: web, solo backend en este slice.
**Performance Goals**: el peor caso de `buscar` son ~2 min (2 requests × 2 intentos × 30 s). El caso medido son ~5 s.
**Constraints**:
- SODA sin `$order`, con una página de 5.000.
- El token es opcional y viaja en el header.
- Los tests no tocan la red.

**Scale/Scope**: un adaptador, un YAML de 58 cámaras, una migración.

## Constitution Check

| Principio | Cómo se cumple | Chequeo |
|---|---|---|
| I. Hexagonal | Adaptador en `infraestructura/adaptadores/datos_gov_co_rues.py`, en el catálogo y en `fuentes.yaml`. El dominio no lo conoce. `camaras.py` en `aplicacion/`, porque solo lee YAML. | `lint-imports`, la suite de contrato con `[datos_gov_co_rues]` y `test_todo_adaptador_de_registro_esta_declarado` (002) |
| II. Test primero | Cada tarea Rojo → Verde. Las guardas que nacen verdes se comprueban por mutación a mano. | `tasks.md` |
| III. RLS | `naturales_por_fuente` vive en `busquedas`, que ya tiene RLS (002). `fuente_cache` es global y sin datos de tenant ni de personas. | `test_rls.py` suma la columna al assert |
| IV. Migraciones | Una `supabase/migrations/NNNN_naturales_por_fuente.sql` a mano (número en D8). | `test_migraciones.py` y el drift check |
| V. Seguridad | `DATOS_GOV_CO_APP_TOKEN` y `DATOS_GOV_CO_URL` desde `settings`, nunca literales. El token va en `X-App-Token` y nunca en la URL, en `url_origen` ni en los logs. El SoQL solo interpola valores validados (CIIU `^\d{4}$` y cámaras del YAML). | `test_app_token_va_en_header_y_nunca_en_logs`, `test_departamento_se_traduce_a_camaras` (inyección), `security` en el PR |
| VI. Contacto sensible | El dataset no trae contacto. El `$select` es una lista blanca que nunca pide nombres, apellidos ni el representante legal. Los descartes no se loguean. | `test_select_no_pide_columnas_de_personas`, `test_descartados_no_se_loguean` |
| VII. Cumplimiento | Jurídica en el servidor y defensa en el cliente. Las naturales se cuentan, no se guardan. `cumplimiento` con `CC-BY-SA-4.0`, `url_origen` y `as_of`. | `test_query_filtra_juridicas_en_servidor`, `test_cliente_descarta_lo_que_no_debio_llegar`, `test_habilitada_por_yaml_temporal_da_leads_cc_by_sa`, `test_naturales_se_guardan_como_conteo` |
| VIII. Costos | `socrata_descarga` por intento, fallidos incluidos, con los segundos del request y `computo_seg_usd` como `Decimal`. | `test_registra_segundos_de_cada_intento`, `test_socrata_descarga_escribe_fila_en_costos`, `test_todo_adaptador_de_registro_recibe_registro_costos` (002) |
| IX. Evals | No aplica: no hay IA. | — |
| X. Doc | `docs/arquitectura-backend.md`: cómo se conecta y se desconecta una fuente, y por qué la natural se cuenta. Si se corta, quedan 5 líneas mínimas. | step de CI de doc por módulo |

**Desvío declarado: `url_origen` con query string.** El invariante de la 002 (plan 002, línea 65) dice "sin query string ni API key". Acá `url_origen` es `…/c82u-588k.json?nit=<nit>`, porque así el origen se puede reproducir por empresa. El `?nit=` no lleva nada secreto: es el identificador público de la matrícula y no lleva token ni datos del tenant. Lo cubre `test_app_token_va_en_header_y_nunca_en_logs`, que además afirma que el token no aparece en ningún `url_origen`. **El invariante de la 002 debería decir "sin API key ni token"**. Ese cambio lo hace el coordinador en la rama de la 002, no esta spec.

**Desvío declarado:** regla 4 de `cumplimiento-datos`. Las naturales "se guardan, no se contactan", pero acá ni se guardan. Es el lado seguro y la skill se anota en el paso 1. No hace falta Complexity Tracking.

## Qué se usa de la 002 y la 003 tal cual

- **Puerto `FuenteDescubrimiento`.** El método es `buscar(criterios, pagina) -> PaginaEmpresas` y `meta` es un **atributo**, no un método. `PaginaEmpresas.total` es `None` en este adaptador: el total exacto lo da `contar`, y una sola página de 5.000 no es un total. Los errores son `CriterioNoSoportado`, `LimiteFuenteAgotado` y `FuenteNoDisponible`, todos del 002.
- **`MetaFuente`.** Se arma desde la entrada del YAML (002) y tiene `clave, proveedor, paises, filtros, trae, tipo, licencia, endpoint, tipo_titular_implicito`.
- **`cargar_registro(ruta_yaml, catalogo)`.** El catálogo `clave → clase` vive en `infraestructura/adaptadores/__init__.py`, y la suite de contrato está parametrizada sobre él con sus fábricas en `tests/contratos/fabricas.py`.
- **Costos.** `OperacionCosto`, `RegistroCostos` (`costos/dominio/`) y `postgres_costos` (`costos/infraestructura/`). El `lote_id` es el `busqueda_id`, que llega por el constructor.
- **`fuente_cache`.** Lleva `(proveedor, endpoint, hash_params)` UNIQUE, es global y no tiene RLS. La columna del cuerpo es `respuesta`.
- **`costos.tipo`.** El CHECK de la 002 (plan 002, línea 210) ya incluye `socrata_descarga`, así que la 011 no lo toca.
- **De la 003.** De ahí vienen `seleccionar_fuentes(registro, criterios, actividades)` con sus `ignorados`, `PaginaEmpresas.truncado` y `descartados_sin_nombre`, el dedup en 4 reglas y la fila de `cumplimiento` por lead nuevo en `EjecutarBusqueda`. También el patrón de costo por intento de `overpass_query`, donde la espera no se cobra, y el patrón de reloj y transporte inyectables.
- **De la 002.** Los tests `test_registro.py::test_carga_config_fuentes_yaml_real_sin_error` (T008), `test_rls.py` (T017), `test_costos_repo.py` (T024), `test_registro_adaptadores.py` y `test_costos_por_adaptador.py` (T036), y `test_cli.py` (T040).

## Preguntas abiertas

Cada una dice qué tareas bloquea. Si el puerto de la 002 o la 003 todavía puede cambiar, se anota como dependencia y no se inventa.

| # | Pregunta | Bloquea | Default propuesto |
|---|---|---|---|
| D1 | La spec escribía `meta()` y el plan de la 002 define `meta` como **atributo**. | T012+ (todo el adaptador) | **Resuelta:** atributo. Los tests se escriben `adaptador.meta.…`. `spec.md` ya está corregida. |
| D2 | **Origen de `cuenta_naturales` y de `costo_maximo_llamada`.** | T020, T040 | **Resuelta:** `cuenta_naturales` va en el YAML y el loader le da default `False`, igual que `licencia`. `costo_maximo_llamada` es de la 005: la 011 no lo agrega (ver D7). |
| D3 | **Forma final de `PaginaEmpresas`.** Depende de la P1 de la 003. | T019, T020, T026 | **Resuelta:** campos aditivos con default sobre lo que deje la 003, sin cambiar ningún adaptador existente. Este adaptador devuelve `total=None`, y lo afirma T026. |
| D4 | **¿Dónde va `licencia`?** | T024 | **Resuelta:** en `meta`, no en `EmpresaCruda`. T024 afirma `adaptador.meta.licencia == "CC-BY-SA-4.0"`. Los demás campos de `EmpresaCruda` (`telefono`, `email`, `geo`) se afirman en `None` si existen después de la 003. |
| D5 | **Columna del caché.** | T031, T032 | **Resuelta:** `respuesta`, como en la 002. `spec.md` ya está corregida. |
| D6 | **Estado "completada".** | — (era T047, movida a la 005 por D7) | **Resuelta:** pasa a la 005, que es la dueña de los estados. |
| D7 | **Tests que dependen de la 005 dentro del PR de la 011.** | T035, T047–T049 | **Resuelta (dueño):** salen de la 011 y se mueven a `specs/005` (rama `docs/005-plan`) estos 6: `test_costo_maximo_llamada` y los 3 tests de `contar` de la suite de contrato de la 005 (de T035), `test_tablero_trae_naturales_por_fuente` (T047) y `muestra_naturales_encontradas_no_contactables` (T048). T049 se va con ellos. En la 011 quedan `test_contar_usa_count_con_el_mismo_where` y `test_contar_registra_socrata_descarga`, con rojo real por aserción sobre un stub de `contar`: sin `xfail`, `ImportError` ni `AttributeError`. |
| D8 | **Número de la migración.** | T042 | **Resuelta:** el siguiente libre después de la `0003` al momento del merge, previsiblemente `0004`. Se elige después de la puerta T001. |
| D9 | **Dónde viven `DATOS_GOV_CO_URL` y `DATOS_GOV_CO_APP_TOKEN`.** | T012, T033, T034 | **Resuelta:** en `settings`, igual que la 003 con Overpass. La fábrica se los pasa al adaptador, que no lee `os.environ`. Los tests usan `monkeypatch.setenv` y construyen un `settings` nuevo. |
| D10 | **Tests que arman el registro desde el YAML real.** Pasar a `habilitado: true` puede cambiar lo que esperan, por ejemplo `test_icp_colombia_completo_usa_las_dos_fuentes`. | T040 | **Resuelta:** después de la puerta se listan con `grep -rn "config/fuentes.yaml" backend/tests` **y** con los usos de la ruta por defecto de `cargar_registro` (`grep -rn "cargar_registro(" backend`, donde una llamada sin ruta explícita lee el YAML real). Se actualizan en el mismo commit que el YAML. |
| D11 | **Ni la 002 ni la 003 crean `test_conectar_desconectar.py`.** | T043 | **Resuelta:** lo crea la 011. Si la 003 terminó agregando `test_yaml_real_no_toca_datos_gov_co`, se renombra y se invierte. |
| D12 | **Puerta.** La 002 y la 003 en main, y después se mergea main en esta rama. | T001 (todo salvo T004 y T005) | **Resuelta:** merge, no rebase. |

## Project Structure

### Documentation (this feature)

```
specs/011-datos-gov-co/
├── spec.md
├── plan.md      # este archivo
└── tasks.md
```

### Source Code

```
backend/
├── config/
│   ├── fuentes.yaml                       # datos_gov_co_rues: habilitado true, dataset, filtros, trae (+ cuenta_naturales si D2)
│   └── camaras_co.yaml                    # nuevo: 58 cámaras → departamentos DIVIPOLA
├── app/
│   ├── cli.py                             # lee FUENTES_YAML; imprime naturales y descartados_no_juridica
│   ├── config.py (settings)               # DATOS_GOV_CO_URL, DATOS_GOV_CO_APP_TOKEN (D9)
│   └── modulos/descubrimiento/
│       ├── dominio/                       # PaginaEmpresas +2 campos, MetaFuente +cuenta_naturales (D2, D3)
│       ├── aplicacion/
│       │   ├── camaras.py                 # nuevo: cargar_camaras, camaras_de
│       │   └── ejecutar_busqueda.py       # guarda naturales_por_fuente
│       └── infraestructura/adaptadores/
│           ├── __init__.py                # + "datos_gov_co_rues"
│           └── datos_gov_co_rues.py       # nuevo
└── tests/
    ├── fixtures/datos_gov_co/{filas.json, filas_descartables.json, conteo_naturales.json}
    ├── unit/
    │   ├── conftest.py                    # fixture autouse sin_red
    │   ├── test_sin_red.py
    │   ├── test_cli.py                    # + test_respeta_fuentes_yaml_del_entorno
    │   └── descubrimiento/{test_datos_gov_co.py, test_camaras_co.py, test_registro.py, test_seleccion_fuentes.py}
    ├── contratos/{conftest.py, fabricas.py, test_fuente_descubrimiento.py}
    └── integration/{test_conectar_desconectar.py, test_costos_repo.py, test_rls.py}
supabase/migrations/NNNN_naturales_por_fuente.sql   # D8
.claude/skills/{fuentes-publicas,cumplimiento-datos}/SKILL.md
docs/arquitectura-backend.md
```

**Structure Decision**: el módulo `descubrimiento` existente. No se crea ningún módulo nuevo.

## Diseño, punto por punto

- **Transporte inyectable.** El adaptador recibe por constructor un `httpx.Client` o `httpx.MockTransport`, más un reloj, `RegistroCostos`, el caché, las cámaras ya cargadas, las tarifas, `lote_id` y la meta. Los tests usan `MockTransport` y cuentan requests ahí. No hay `respx`: `MockTransport` ya viene en `httpx`.
- **Reintento.** Un solo bucle `for intento in range(2)`. Cada intento mide `reloj()` antes y después, registra la fila y después decide. La espera de 1 s pasa por un `dormir` inyectable y no se mide.
- **`FuenteNoDisponible(f"datos.gov.co {status}")`.** Lleva solo el código de estado, sin `response.text`.
- **Orden dentro de `buscar(p=1)`.** Primero valida y traduce, sin I/O. Después vienen las filas (desde el caché o la red), el conteo (desde el caché o la red, y si falla da `None`, que no se cachea), el mapeo y el armado de `PaginaEmpresas`.
- **Filtro del cliente.** Una función pura `_es_juridica_valida(fila) -> bool` evalúa los casos (a) a (d). (a) compara `organizacion_juridica.strip().upper() == "PERSONA NATURAL"`, para que no se escape una variante de mayúsculas o espacios (caso a'). Solo cuenta lo descartado y nunca lo pasa a `logger`.
- **Hash del caché.** `sha256` del JSON de los parámetros SoQL ordenados (`sort_keys=True`). Lleva un discriminador `tipo: filas|naturales` dentro de los parámetros, para que las dos claves sean distintas aunque el `$where` coincida. `contar` no se cachea en la 011: la 005 suma su clave junto con su test de hit de caché (YAGNI).
- **`as_of`.** `email.utils.parsedate_to_datetime(header)`, de la stdlib. Sin header, `reloj()`.
- **`ciudad`.** `camaras[codigo_camara].municipio_sede`. Si la cámara de la fila no está en el YAML, `ciudad = None`. No se descarta, porque es jurídica válida.
- **`naturales_por_fuente`.** `EjecutarBusqueda` arma `{clave: pagina.naturales_no_descargadas}` solo para las fuentes con `meta.cuenta_naturales`, y lo escribe con el `UPDATE` de cierre de la búsqueda.
- **Fixture `sin_red`.** Parchea `socket.socket.connect` y `connect_ex` con `monkeypatch`. Deja pasar `AF_UNIX` y `ipaddress.ip_address(host).is_loopback`. Si el host no es una IP literal, bloquea: es el lado seguro. Para todo lo demás lanza `RedBloqueadaEnTests(OSError)`. Vive en un helper compartido, `tests/_sin_red.py`, importado por los dos `conftest.py`, para no duplicarla.

## Orden de tareas (TDD)

Sigue los pasos 1 a 11 de la spec. El detalle está en `tasks.md`. El advisor revisa los tests del paso 4 (filtro jurídico, principio VII) y los de costos del paso 6 (principio VIII) **antes** de aceptarlos.

## Complexity Tracking

Sin violaciones que justificar. Las simplificaciones `# ponytail:` de la spec (una página de 5.000, cámara en lugar de municipio, último conteo y no suma, sin bloqueo de DNS) quedan como comentarios en el código, en la línea que las implementa.
