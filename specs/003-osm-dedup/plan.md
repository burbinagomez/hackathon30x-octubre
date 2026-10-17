# Implementation Plan: 003 — OSM Overpass, normalización común y dedup en 4 niveles

**Branch**: `feature/003-osm-dedup` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Formato de `/speckit-plan` aplicado a mano: `setup-plan.sh` no resuelve el feature (falta `.specify/feature.json`). No se generan `research.md`, `data-model.md`, `contracts/` ni `quickstart.md`: la spec ya fija las decisiones, las tablas y los contratos con un nivel de detalle que esos archivos solo repetirían. Lo que la spec no resuelve está en **Preguntas abiertas**.

## Summary

Segundo adaptador de `FuenteDescubrimiento` (`osm_overpass`, ciudad + tipo de negocio), selección de fuentes por ICP como función pura del dominio, normalización común (nombre, ciudad, dominio, E.164), dedup en 4 niveles con veto por `id_fiscal` distinto y cola de revisión, y cifrado en reposo de `telefono`/`email` con HMAC para la regla 3. Una migración: `supabase/migrations/0003_osm_dedup.sql`. En BR y PE, OSM es la única fuente que la selección deja pasar.

El registro mercantil no entra como fuente de este slice: Supersociedades (vía Croma) es la única fuente de registro que descubre, y su papel en el dedup es aportar `id_fiscal` (regla 1, y veto en las otras tres). La verificación contra RUES es del 006.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: las del 002 (FastAPI, SQLAlchemy 2, psycopg 3, `httpx`, PyYAML) + **nuevas**: `phonenumbers` (pura, permitida en `dominio/`), `cryptography` (AES-256-GCM, HKDF; la stdlib no trae AES)
**Storage**: Postgres (Supabase en prod, `postgres:16` en CI). `pg_trgm` en el esquema `extensions`. Tabla nueva `revision_dedup`; columnas nuevas en `leads`
**Testing**: pytest (unit con puertos falsos, integración con `app_rt` y `pg_trgm` real, arquitectura), `httpx.MockTransport`, reloj y `sleep` falsos
**Target Platform**: Railway (`api`), CLI `app.cli buscar`
**Project Type**: web app (backend); este slice no toca `frontend/`
**Performance Goals**: N/A. Overpass ≤ 1 req/s, tope de 500 elementos por query
**Constraints**: ≤ 4 h con los cortes de la spec (~5 h completo); sin red en tests; una sola corrida real contra Overpass, avisada antes
**Scale/Scope**: 1 ciudad por búsqueda, ≤ 500 elementos OSM, decenas a cientos de leads

## Constitution Check

*GATE: antes de empezar y re-chequeado tras el diseño.*

| Principio | Qué entrega este slice | Estado |
|---|---|---|
| I Hexagonal | `osm_overpass` en `infraestructura/adaptadores/`, registrado en `config/fuentes.yaml` (`habilitado: true`, ya presente) y en el catálogo; pasa la suite de contrato del 002 sin tocarla. Normalización, selección y dedup en `dominio/` como funciones puras. Los cargadores de `actividades.yaml` y `dedup.yaml` en `aplicacion/`. `phonenumbers` en dominio se declara en el contrato de import-linter. | ✅ (ver P5) |
| II Test primero | Cada tarea de `tasks.md` es un par rojo → verde, el rojo por la razón correcta. Advisor revisa RLS, cifrado, dedup y costos antes de aceptar. | ✅ |
| III Tenant/RLS | `revision_dedup` con `tenant_id` y RLS; se suma al parametrizado de `test_rls.py`. `test_privilegios_supabase` la toma sola (lee `pg_tables`). | ✅ |
| IV Migraciones | Una migración a mano, `0003_osm_dedup.sql`. `test_pg_trgm_en_extensions_y_usable_por_app_rt` sobre `base_vacia`. El drift check del 001/002 cubre la `0003` sin cambios. | ✅ |
| V Seguridad pipeline | `CIFRADO_KEY` y `OVERPASS_URL` desde el entorno vía `settings`; la app no arranca sin `CIFRADO_KEY` (`ConfigInvalida`). `CIFRADO_KEY` no choca con el guard de `config.py` (no es `SUPABASE_*` ni prefijo prohibido). Dos dependencias nuevas pasan por `pip-audit`. | ✅ |
| VI Contacto cifrado | `Cifrador` (AES-GCM, AAD `tabla.columna`) y HMAC del E.164 en `app/seguridad/`; catálogo `catalogo_sensibles.py`; tests de catálogo, de columnas fuera del catálogo, de logs y de `wa.me` en columnas no catalogadas. Sin caché de Overpass (la respuesta cruda trae contacto en claro). | ✅ |
| VII Cumplimiento | Lead OSM con `tipo_titular='desconocido'` (no contactable hasta el 006), fila en `cumplimiento` con `licencia='ODbL'` y `url_origen` del elemento. `telefono_canal`/`email_canal` etiquetan el canal publicado; un dato de registro no es canal. Fusionar no toca `cumplimiento`; `tipo_titular` sube y nunca baja. Este slice no envía nada. | ✅ |
| VIII Costos | `overpass_query` por cada intento HTTP, con segundos del request (sin esperas), `computo_seg_usd`, `gratis=false`, `lead_id=None`, `lote_id` de la corrida, escrita antes de devolver. Test unitario + integración con `postgres_costos` real. | ✅ (ver P6, P9) |
| IX Evals | N/A: sin IA. | — |
| X Doc viva | `docs/arquitectura-backend.md`: normalización, dedup, cifrado, cómo mapear un CIIU nuevo y cómo agregar un host compartido. Primer corte si el tiempo aprieta (deuda anotada en el PR). | ⚠️ |

Re-chequeo post-diseño: sin violaciones nuevas. El ⚠️ de X es el corte 1 de la spec.

## Qué se usa del 002 tal cual

Lo que la spec del 002 fija y este slice consume sin cambiarlo:
- `FuenteDescubrimiento.buscar(criterios, pagina)` y su suite de contrato (los 3 tests, parametrizados sobre el catálogo).
- `cargar_registro(ruta_yaml, catalogo)`, el catálogo `clave → clase` en `infraestructura/adaptadores/__init__.py`, `sin_implementacion`, `RegistroInvalido`.
- `CriterioNoSoportado` como red de seguridad del adaptador; `LimiteFuenteAgotado` del adaptador Croma.
- `RegistroCostos` con `registrar`, `requests_24h(proveedor)` y `creditos_mes(proveedor)`. Las filas de OSM llevan `proveedor='osm'`, así que no cuentan para los límites de Croma.
- `EmpresaCruda` con `actividad == (codigo, sistema)` y `id_fiscal` normalizado.
- Tablas `leads`, `lead_fuentes`, `cumplimiento`, `costos` de la `0002`, el `UNIQUE (tenant_id, pais, id_fiscal)` y el `ON CONFLICT DO NOTHING` de `lead_fuentes`.
- La unidad de trabajo con `SET LOCAL app.tenant_id`, `EXCLUIDOS` de `persistencia/` (este slice no agrega archivos ahí), `base_vacia` y `supabase_simulado.sql`.

Lo que la **spec del 003** agrega a esos puertos, y nada más:
- `EmpresaCruda` + `telefono_canal`, `email_canal` (opcionales, default `None`).
- `RepositorioLeads` + `por_dominio`, `por_telefono`, `candidatos_por_nombre` (listas) y `registrar_revision`.
- Tipo `overpass_query` en el libro de costos.

## Preguntas abiertas

Cosas que la 003 necesita y la spec del 002 no fija. No se inventan acá: cada una bloquea las tareas que la citan en `tasks.md` hasta que la resuelva el plan del 002 (o una enmienda de la spec).

| # | Qué falta | Dónde falta en la spec 002 | Bloquea |
|---|---|---|---|
| P1 | El tipo de retorno de `buscar`. La skill lo llama `PaginaEmpresas`, pero la 002 no lo define. La 003 necesita que lleve, por fuente, `truncado` y `descartados_sin_nombre` (tests `test_quinientos_elementos_marca_truncado`, `test_elemento_sin_nombre_se_descarta_y_se_cuenta`, y el resumen de la CLI). ¿Existe ese objeto y admite esos dos campos, o hay que agregarlos? | §Flujo principal, paso 2 (`buscar(criterios, pagina)` sin retorno); §Decisiones técnicas → Módulo (la lista de `dominio/` no lo nombra) | T039–T040, T049–T052 |
| P2 | Los campos de `EmpresaCruda`. La 002 solo fija los que asertan sus tests (`pais`, `nombre`, `fuente`, `url_origen`, `as_of`, `actividad`, `id_fiscal`, `tipo_titular`, `ciudad`, `direccion`). La 003 aserta además `web`, `telefono`, `email`, `geo` y `licencia`, y declara que solo suma `telefono_canal`/`email_canal`. ¿Esos cinco ya están en la `EmpresaCruda` del 002? ¿Qué tipo tiene `geo` (par `lat/lon`, objeto)? ¿`licencia` va en la empresa o en `MetaFuente`? | §Decisiones técnicas → Módulo; §Terminado cuando → Contrato del puerto (`test_devuelve_empresas_normalizadas`) y Adaptador Croma (`test_mapea_respuesta_a_empresa_cruda`) | T039–T040, T045–T046 |
| P3 | La forma de `CriteriosICP`. La 003 necesita `ciudad`, `tipo_negocio` (conjunto de etiquetas OSM) e `ingresos_min`, y que la selección arme un subconjunto por fuente (los no declarados "no se le pasan"). ¿Es un dataclass con opcionales, un mapeo, o algo que permita saber qué criterios vienen presentes? | §Decisiones técnicas → Módulo (lo nombra sin campos); §Contrato del puerto (`test_rechaza_criterio_no_soportado` supone que se puede pasar un criterio arbitrario) | T014–T016 |
| P4 | Qué devuelve `cargar_registro` y cómo se leen `paises`/`filtros` de cada entrada. `seleccionar_fuentes(registro, criterios, actividades)` los lee del registro. ¿Salen de la entrada del YAML, de `MetaFuente` en la instancia, o de los dos? | §Decisiones técnicas → Registro; §Flujo principal, paso 2 | T014–T016 |
| P5 | Cómo se construye cada adaptador y cómo lo construye la suite de contrato. El catálogo es `clave → clase` y "el dominio recibe instancias ya construidas", pero no se fija quién instancia ni con qué argumentos. OSM necesita `RegistroCostos`, transporte, `costo_unitario`, `hosts_compartidos` (`frozenset`), reloj, `sleep` y URL. La 003 promete que la suite "no se toca": si la suite arma cada adaptador con una fábrica por clave, sumar OSM es agregar su fábrica de prueba; si no, hay que tocarla. ¿Qué criterio usa `test_rechaza_criterio_no_soportado`? Tiene que caer fuera de los `filtros` de OSM también. | §Decisiones técnicas → Registro ("el dominio recibe instancias ya construidas"); §Terminado cuando → Contrato del puerto | T037–T044, T047–T048 |
| P6 | De dónde sale el `lote_id` "de la corrida" que lleva cada fila de costo. ¿Constructor, argumento de `buscar`, parte de `CriteriosICP`, contexto de la unidad de trabajo? Y si `OperacionCosto.ts` sale del reloj inyectable o de `now()` de la base. | §Terminado cuando → Adaptador Croma (`test_registra_un_credito_por_request`: "el `lote_id` de la corrida") | T041–T044 |
| P7 | La entidad `Lead` y los métodos base de `RepositorioLeads`. La 002 nombra el puerto sin métodos. `resolver_duplicado` necesita una entidad de dominio con `id`, `creado_en`, `id_fiscal`, `tipo_titular`, `geo`, (`telefono`, `telefono_canal`), (`email`, `email_canal`) y dominio, y la búsqueda de la regla 1 por `(pais, id_fiscal)`. Además, **ningún método fija la escritura de la fusión** (`coalesce` de nulos, par dato+canal, `tipo_titular` que sube): la 002 dice "lead existente: se reutiliza y no se toca", y la 003 solo agrega los cuatro métodos de lectura/revisión. El hueco es también de la spec 003 (§Puertos y adaptadores, `RepositorioLeads`). | §Decisiones técnicas → Módulo (`RepositorioLeads` sin métodos); §Flujo principal, paso 4 ("se reutiliza y no se toca `cumplimiento`") | T025–T026, T028–T036, T049–T051 |
| P8 | `FuenteNoDisponible`. La 003 la usa (fallo tras el reintento de OSM y caída de una fuente sin perder las otras) y la 002 no la define: solo `CriterioNoSoportado`, `LimiteFuenteAgotado` y `RegistroInvalido`. ¿La define el 002 para Croma (su riesgo dice "el error se reporta en la búsqueda; no se traga")? ¿`EjecutarBusqueda` del 002 ya aísla el fallo por fuente? ¿`LimiteFuenteAgotado` se reporta como caída? | §Riesgos ("Croma devuelve 502 o tarda"); §Decisiones técnicas → HTTP | T041, T044, T049, T051 |
| P9 | `costos.tipo`: ¿lleva `CHECK` o es texto libre? ¿`TipoOperacion` es `Literal`/`Enum` en dominio? Si hay `CHECK`, la `0003` lo amplía con `overpass_query`. | §Decisiones técnicas → Tablas, fila `costos` ("las columnas de `OperacionCosto` + `gratis`") | T024, T044 |
| P10 | El cargador de `tarifas.yaml`. La 003 exige `Decimal(str(valor))` para comparar `Decimal("0.0000070")`. Si el del 002 convierte de otra forma, este slice lo cambia (toca código del 002). | §Decisiones técnicas → Tarifas | T041–T044 |
| P11 | La forma de `sin_fuente_para(pais, criterio)` y dónde vive la selección. La 002 la pone en el orquestador (paso 2) y la 003 la mueve a `dominio/seleccion.py`. ¿Qué tipo tiene `sin_fuente_para` y cómo convive con los `ignorados` por motivo (`pais`, `sin_mapeo_actividad`, `sin_geografia`)? `test_sin_fuente_para_el_pais_se_reporta` del 002 tiene que seguir verde. | §Flujo principal, paso 2; §Terminado cuando → Caso de uso (`test_sin_fuente_para_el_pais_se_reporta`) | T014–T016 |

Sin bloqueo (no dependen de ninguna P): normalización, `geo.py`, `dedup.yaml`, `actividades.yaml` y su cargador, `Cifrador`, `ConfigInvalida`, la `0003` (salvo P9) y `clasificar_similitud`.

## Project Structure

### Documentation (this feature)

```text
specs/003-osm-dedup/
├── spec.md
├── plan.md     # este archivo
└── tasks.md
```

### Source Code

```text
backend/
├── pyproject.toml                      # + phonenumbers, cryptography; import-linter: phonenumbers en dominio
├── config/
│   ├── fuentes.yaml                    # sin cambios: osm_overpass ya está habilitado con paises/filtros/licencia
│   ├── actividades.yaml                # nuevo: CIIU → etiquetas OSM (4711, 5611, 4752)
│   └── dedup.yaml                      # nuevo: hosts_compartidos
├── app/
│   ├── config.py                       # + cifrado_key, overpass_url; ConfigInvalida sin CIFRADO_KEY
│   ├── cli.py                          # (del 002) + --ciudad, resumen por fuente
│   ├── seguridad/
│   │   ├── cifrado.py                  # Cifrador: AES-256-GCM + HMAC-SHA256, subclaves HKDF
│   │   └── catalogo_sensibles.py       # leads.telefono_cifrado, leads.email_cifrado
│   └── modulos/descubrimiento/
│       ├── dominio/
│       │   ├── normalizacion.py        # normalizar_nombre/ciudad/dominio, a_e164
│       │   ├── geo.py                  # haversine
│       │   ├── dedup.py                # resolver_duplicado, clasificar_similitud, umbrales, DISTANCIA_MAX_FUSION_M
│       │   └── seleccion.py            # seleccionar_fuentes
│       ├── aplicacion/
│       │   ├── configuracion.py        # cargar_actividades, cargar_hosts_compartidos (junto a cargar_registro)
│       │   └── ejecutar_busqueda.py    # (del 002) normaliza + resolver_duplicado + resumen por fuente
│       └── infraestructura/
│           ├── adaptadores/
│           │   ├── __init__.py         # catálogo + osm_overpass
│           │   ├── osm_overpass.py
│           │   └── croma_supersociedades.py   # + geo; canales en None
│           └── persistencia/
│               └── repositorio_leads.py       # + por_dominio, por_telefono, candidatos_por_nombre, registrar_revision; cifra/hashea
└── tests/
    ├── unit/seguridad/test_cifrador.py
    ├── unit/descubrimiento/{test_normalizacion,test_seleccion_fuentes,test_dedup,test_osm_overpass}.py
    ├── unit/descubrimiento/{test_registro,test_croma_supersociedades}.py   # del 002, se actualizan
    ├── contratos/test_fuente_descubrimiento.py                             # del 002, + [osm_overpass]
    ├── fixtures/osm/                                                       # respuestas Overpass sintéticas
    ├── integration/{test_dedup_repo,test_busqueda_dos_fuentes}.py
    ├── integration/{test_costos_repo,test_rls}.py                          # del 002, + casos
    └── arquitectura/{test_cifrado,test_migraciones}.py                     # test_migraciones del 001/002, + pg_trgm
supabase/migrations/0003_osm_dedup.sql
docs/arquitectura-backend.md
```

**Structure Decision**: todo dentro del módulo `descubrimiento` del 002, salvo `app/seguridad/`, que la spec pone fuera porque la reusan el 006 y el 007. Un solo archivo nuevo de configuración de aplicación (`configuracion.py`) para los dos cargadores; si el 002 ya tiene un archivo para `cargar_registro`, van ahí.

## Diseño, punto por punto

**Registro y selección.** `osm_overpass` ya está en `fuentes.yaml` con `habilitado: true`, `paises: [CO, MX, PE, BR, "*"]`, `filtros: [ciudad, tipo_negocio]` y `licencia: ODbL`; el slice solo lo agrega al catálogo, y `sin_implementacion` pasa a `{"croma_dian_trade_co"}`. `seleccionar_fuentes` (pura) aplica país → actividad → geografía y devuelve, por fuente, los criterios filtrados o el motivo de ignorarla. Con el `fuentes.yaml` real, para BR y PE solo queda `osm_overpass`: Supersociedades y DIAN Trade son `paises: [CO]`, SIEM está deshabilitado y `datos_gov_co_rues` también. Se suma un test para PE (no está en la spec) con el YAML real, igual que el de BR.

**Adaptador OSM.** Query única con unión de etiquetas, `[out:json][timeout:25]`, área ciudad dentro del país, tope 500. URL por constante con override `OVERPASS_URL` desde `settings` (no se lee el entorno en el adaptador). User-Agent identificable con versión y URL del repo, armado desde `settings`. Limitador por proceso con reloj y `sleep` inyectables (`# ponytail:` contador compartido si hay varios workers). Un reintento ante 429/504: `Retry-After` con tope 10 s; sin él, `max(1, limitador)`. Una fila `overpass_query` **por intento**, con los segundos del request y no los de la espera, escrita antes de devolver o de lanzar. El mensaje de `FuenteNoDisponible` no lleva el cuerpo de la respuesta. El mapeo usa `normalizar_dominio` y `a_e164` del dominio; el `wa.me` va a `telefono` con `whatsapp_osm` solo si no hay otro teléfono válido, y su URL nunca se guarda en `web`.

**Croma (del 002).** Solo suma `geo` desde `lat/lon` de la fixture, y deja `telefono_canal`/`email_canal` en `None`.

**Dedup.** `resolver_duplicado` en dominio, con el repositorio por puerto: regla 1 `(pais, id_fiscal)` → 2 dominio (sin hosts compartidos) → 3 HMAC del E.164 → 4 nombre normalizado + ciudad normalizada con similitud de `pg_trgm`. Veto por `id_fiscal` distinto en cualquier regla, que excluye al candidato y sigue. Desempate en dominio (no en el `ORDER BY`): reglas 1–3 por `creado_en` asc; regla 4 por similitud desc y `creado_en` asc, buscando el primero que cumple fusión (≥ 0,92, geo en los dos, ≤ 250 m) antes de caer a revisión. Fusión: `coalesce`, par (dato, canal) por confianza, `tipo_titular` sube, `lead_fuentes` suma, `cumplimiento` intacto. Revisión: lead nuevo con su `cumplimiento` + fila `pendiente` en `revision_dedup` con el par ordenado.

**Cifrado.** `Cifrador` con dos subclaves HKDF de `CIFRADO_KEY`: AES-256-GCM (nonce de 12 bytes como prefijo, AAD `tabla.columna`) y HMAC-SHA256 del E.164. El repositorio cifra y hashea al escribir, descifra al leer; el dominio nunca ve bytes. El valor en claro no se loggea en ningún nivel, tampoco en `httpx`.

**Migración `0003`** (a mano): `CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions`; columnas nuevas de `leads` con los `CHECK` de canal y de dato ⇔ canal; índice GIN con `extensions.gin_trgm_ops`; btree no únicos en `(tenant_id, dominio)` y `(tenant_id, telefono_hmac)`; `revision_dedup` con RLS, `CHECK (lead_a < lead_b)` y `UNIQUE (lead_a, lead_b)`; `GRANT` a `app_rt`. Si P9 dice que `costos.tipo` tiene `CHECK`, se amplía acá.

**Costos y cumplimiento.** Ninguna operación de salida nueva sin fila: la única es el `POST` a Overpass. Cumplimiento por lead OSM nuevo: `fuente='osm_overpass'`, `licencia='ODbL'`, `url_origen` del elemento, `as_of` de la base OSM, `base_legal` nula hasta el 007. Este slice no contacta a nadie, así que el chequeo de envío (`tipo_titular == 'juridica'`, canal publicado, fila en `cumplimiento`) no se ejercita; lo que sí deja es el dato para que el 006/007 lo evalúe.

## Orden de tareas (TDD)

El de la spec (§Plan de tareas), con la puerta del 002 adelante:

0. **Puerta:** el 002 mergeado en `main` y esta rama rebasada; P1–P11 respondidas.
1. Normalización, `geo.py` y `dedup.yaml`.
2. Selección de fuentes y `actividades.yaml`.
3. `Cifrador` y `ConfigInvalida`.
4. Migración `0003` (pg_trgm → RLS → cifrado de catálogo). Advisor revisa RLS y cifrado.
5. Dedup en dominio. Advisor revisa los tests.
6. Repositorio contra `pg_trgm` real.
7. Adaptador OSM y su test de costos en integración. Advisor revisa los tests de costos.
8. Suite de contrato con `[osm_overpass]` y `test_registro.py`.
9. `EjecutarBusqueda` con dos fuentes y test de logs.
10. CLI y una corrida real contra Overpass, avisada antes.
11. `docs/arquitectura-backend.md`.

Los pasos 1, 2 y 3 son independientes entre sí. Los cortes son los de la spec (§Cuándo cortar), en ese orden.

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| Sin `research.md`, `data-model.md`, `contracts/`, `quickstart.md` | La spec ya trae las decisiones (Overpass, cifrado, umbrales), las tablas y los tests; esos archivos la duplicarían. Las incógnitas reales son de la interfaz con el 002 y están en Preguntas abiertas | Generar los cuatro archivos repitiendo la spec |
| `phonenumbers` en `dominio/` | La normalización E.164 es regla de dominio y la librería es pura, sin I/O; la spec lo decide así | Mover `a_e164` a infraestructura y que el dominio reciba el teléfono ya normalizado: el dedup y el adaptador tendrían dos normalizaciones |
| Test extra `test_icp_peru_solo_usa_osm` | El pedido del slice dice "en BR y PE la única fuente es OSM"; la spec solo prueba BR | Confiar en que PE se comporta igual que BR |
| Doc (X) es el primer corte | Lo fija la spec; el 013 la cierra | — |
