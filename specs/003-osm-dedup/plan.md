# Implementation Plan: 003 — OSM Overpass, normalización común y dedup en 4 niveles

**Branch**: `feature/003-osm-dedup` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Formato de `/speckit-plan` aplicado a mano: `setup-plan.sh` no resuelve el feature (falta `.specify/feature.json`). No se generan `research.md`, `data-model.md`, `contracts/` ni `quickstart.md`: la spec ya fija las decisiones, las tablas y los contratos con un nivel de detalle que esos archivos solo repetirían.
>
> Base del 002: su `plan.md` aprobado (rama `feature/002-puertos-registro-supersociedades`, commit `89d3e59`). Las citas "002 plan:N" son líneas de ese archivo en ese commit.

## Summary

Segundo adaptador de `FuenteDescubrimiento` (`osm_overpass`, ciudad + tipo de negocio), selección de fuentes por ICP como función pura del dominio, normalización común (nombre, ciudad, dominio, E.164), dedup en 4 niveles con veto por `id_fiscal` distinto y cola de revisión, y cifrado en reposo de `telefono`/`email` con HMAC para la regla 3. Una migración: `supabase/migrations/0003_osm_dedup.sql`. En BR y PE, OSM es la única fuente que la selección deja pasar.

El registro mercantil no entra como fuente de este slice: Supersociedades (vía Croma) es la única fuente de registro que descubre, y su papel en el dedup es aportar `id_fiscal` (regla 1, y veto en las otras tres) y `tipo_titular='juridica'` al fusionar. La verificación contra RUES (`croma_rues_co`, enriquecedor) es del 006.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: las del 002 (FastAPI, SQLAlchemy 2 Core, psycopg 3, `httpx` y `pyyaml` en runtime, 002 plan:16) + **nuevas**: `phonenumbers` (pura, permitida en `dominio/`), `cryptography` (AES-256-GCM, HKDF; la stdlib no trae AES)
**Storage**: Postgres (Supabase en prod, `postgres:16` en CI). `pg_trgm` en el esquema `extensions`. Tabla nueva `revision_dedup`; columnas nuevas en `leads`. `costos` no cambia
**Testing**: pytest (unit con puertos falsos, integración con `app_rt` y `pg_trgm` real, arquitectura), `httpx.MockTransport`, reloj y `sleep` falsos
**Target Platform**: Railway (`api`), CLI `app.cli buscar`
**Project Type**: web app (backend); este slice no toca `frontend/`
**Performance Goals**: N/A. Overpass ≤ 1 req/s, tope de 500 elementos por query
**Constraints**: ≤ 4 h con los cortes de la spec (~5 h completo); sin red en tests; una sola corrida real contra Overpass, avisada antes; el HTTP corre sin transacción abierta (002 plan:168)
**Scale/Scope**: 1 ciudad por búsqueda, ≤ 500 elementos OSM, decenas a cientos de leads

## Constitution Check

*GATE: antes de empezar y re-chequeado tras el diseño.*

| Principio | Qué entrega este slice | Estado |
|---|---|---|
| I Hexagonal | `osm_overpass` en `infraestructura/adaptadores/`, registrado en `config/fuentes.yaml` (`habilitado: true`, ya presente) y en el catálogo; pasa la suite de contrato del 002 sumando solo su fábrica. Normalización, selección, fusión y dedup en `dominio/` como funciones puras. Cargadores de `actividades.yaml` y `dedup.yaml` en `aplicacion/registro.py`. `phonenumbers` en dominio se declara en import-linter. | ✅ |
| II Test primero | Cada tarea de `tasks.md` es un par rojo → verde, el rojo por la razón correcta. Advisor revisa RLS, cifrado, dedup y costos antes de aceptar. | ✅ |
| III Tenant/RLS | `revision_dedup` con `tenant_id` y RLS; se suma al parametrizado de `test_rls.py`. `test_privilegios_supabase` la toma sola. | ✅ |
| IV Migraciones | Una migración a mano, `0003_osm_dedup.sql`. `test_pg_trgm_en_extensions_y_usable_por_app_rt` sobre `base_vacia`. `app/modelos.py` suma las columnas y la tabla para que el drift check siga vacío. | ✅ |
| V Seguridad pipeline | `CIFRADO_KEY` y `OVERPASS_URL` por `Settings`; la app no arranca sin `CIFRADO_KEY` (`ConfigInvalida`). `CIFRADO_KEY` no choca con el guard de `config.py`. Dos dependencias nuevas pasan por `pip-audit`. | ✅ |
| VI Contacto cifrado | `Cifrador` (AES-GCM, AAD `tabla.columna`) y HMAC del E.164 en `app/seguridad/`; catálogo `catalogo_sensibles.py` (con `nombre_cifrado` y `direccion_cifrada` para titulares no jurídicos, enmienda 2026-10-18; `CONDICIONALES` para `nombre`/`direccion`/`nombre_normalizado` en claro solo si `juridica`); tests de catálogo, de columnas fuera del catálogo (con la lista cerrada que incluye `leads.idioma_contacto` y `fuente_cache.respuesta`, 002 plan:211), de logs y de `wa.me` en columnas no catalogadas. Sin caché de Overpass. | ✅ |
| VII Cumplimiento | Lead OSM con `tipo_titular='desconocido'` (no contactable hasta el 006), fila en `cumplimiento` con `licencia` de `MetaFuente` (`ODbL`) y `url_origen` del elemento, en la misma transacción que el lead (002 plan:178). `telefono_canal`/`email_canal` etiquetan el canal publicado; un dato de registro no es canal. `aplicar_fusion` no toca `cumplimiento`; `tipo_titular` sube y nunca baja. Este slice no envía nada. | ✅ |
| VIII Costos | `overpass_query` por cada intento HTTP, con segundos del request (sin esperas), `computo_seg_usd` como `Decimal`, `gratis=false`, `lead_id=None`, `lote_id=busqueda_id`, escrita antes de devolver o lanzar. Cubierto por `test_costos_por_adaptador` (002), el unitario y la integración con `postgres_costos` real. | ✅ |
| IX Evals | N/A: sin IA. | — |
| X Doc viva | `docs/arquitectura-backend.md` (lo crea el 002, 002 plan:296): normalización, dedup, cifrado, cómo mapear un CIIU nuevo y cómo agregar un host compartido. Primer corte si el tiempo aprieta. | ⚠️ |

Re-chequeo post-diseño: sin violaciones nuevas. El ⚠️ de X es el corte 1 de la spec.

## Qué se usa del 002 tal cual

- Tipos del puerto (002 plan:48-94): `Actividad`, `CriteriosICP(pais, filtros: Mapping[str, str | tuple[str, ...]])`, `EmpresaCruda`, `PaginaEmpresas(empresas, total)`, `MetaFuente` (con `paises`, `filtros`, `licencia`), `FuenteDescubrimiento.meta` + `buscar(criterios, pagina) -> PaginaEmpresas`.
- Errores (002 plan:97-99): `CriterioNoSoportado` antes de cualquier request, `LimiteFuenteAgotado`, `FuenteNoDisponible` con las filas de costo ya escritas.
- `RepositorioLeads` (002 plan:107-116): `crear_busqueda`, `obtener_o_crear_lead(e, licencia)` (lead + `cumplimiento` en una transacción), `agregar_lead_fuente`, `cerrar_busqueda`.
- `OperacionCosto` y `RegistroCostos` en `app/modulos/costos/dominio/` (002 plan:118-139).
- `cargar_registro` → `Registro.fuentes` como `(clase, MetaFuente)` y `Registro.sin_implementacion` (002 plan:143-148); catálogo en `infraestructura/adaptadores/__init__.py` (002 plan:149).
- Raíz de composición en `app/cli.py`: tarifas como `Decimal(str(v))`, adaptadores construidos por búsqueda con `meta`, `RegistroCostos`, transporte, tarifa, límites y `lote_id` (002 plan:150).
- Suite de contrato parametrizada sobre el catálogo, con fábricas en `tests/contratos/fabricas.py`, `test_hay_fabrica_para_cada_clave_del_catalogo` y la centinela `"__criterio_inexistente__"` (002 plan:155-162).
- `EjecutarBusqueda` captura `LimiteFuenteAgotado`/`FuenteNoDisponible` por fuente y cierra `con_errores` (002 plan:295).
- `CHECK` de `costos.tipo` con `overpass_query` ya incluido (002 plan:210).

## Lo que la spec 003 agrega (enmiendas en spec.md §Puertos y adaptadores)

Campos con default o métodos nuevos; ninguno cambia la firma de `buscar` ni de los métodos del 002.
- `EmpresaCruda` + `telefono`, `email`, `geo: Geo | None` (`Geo(lat, lon)`), `telefono_canal`, `email_canal`. La 002 ya lo anticipa (002 plan:103). `licencia` queda en `MetaFuente`.
- `PaginaEmpresas` + `truncado: bool = False`, `descartados_sin_nombre: int = 0`. Va como enmienda de la 003: el 002 dice que un cambio a los tipos de retorno pide spec (002 plan:103).
- `CriteriosICP` sin cambios de tipo: criterio presente = clave de `filtros`; `ciudad: str`, `tipo_negocio: tuple[str, ...]`.
- `RepositorioLeads` + entidad `Lead`, `por_id_fiscal`, `por_dominio`, `por_telefono`, `candidatos_por_nombre`, `registrar_revision` y `aplicar_fusion(lead_id, cambios: CambiosLead)` con `coalesce` en los simples; los pares se reemplazan.
- `seleccionar_fuentes(metas: Iterable[MetaFuente], criterios, actividades) -> (seleccionadas: dict[clave, CriteriosICP], ignoradas: dict[clave, motivo])`.
- `cubre(meta, criterios)` (002 plan:101) queda solo con el país; `test_cubre` del 002 se actualiza (el caso del filtro fuera de `meta.filtros` pasa a verdadero).

## Preguntas abiertas

Ninguna. Las once de la primera versión quedan cerradas así:

| # | Tema | Cerrada por |
|---|---|---|
| P1 | Tipo de retorno de `buscar` | `PaginaEmpresas` en 002 plan:74-77, :96 y :299; `truncado` y `descartados_sin_nombre` como enmienda en spec 003 §Puertos |
| P2 | Campos de `EmpresaCruda` | Base en 002 plan:60-72; `telefono`, `email`, `geo` en spec 003 §Puertos (anticipado en 002 plan:103); `licencia` en `MetaFuente` (002 plan:87) |
| P3 | Forma de `CriteriosICP` | 002 plan:55-58 (`filtros: Mapping[str, str \| tuple[str, ...]]`); "presente = clave del mapeo" en spec 003 §Puertos |
| P4 | Qué devuelve `cargar_registro` | 002 plan:143-147 (`Registro.fuentes` como `(clase, MetaFuente)`) y :79-89 (`MetaFuente.paises`/`filtros`) |
| P5 | Construcción de adaptadores y suite | 002 plan:150 (la CLI construye), :151 (sumar fuente = clase + catálogo + YAML + fábrica), :155-162 (fábricas, `test_hay_fabrica…`, centinela) |
| P6 | `lote_id` y `ts` | 002 plan:150 y :286 (`lote_id = busqueda_id`, por constructor); :291 (`ts` lo pone la base) |
| P7 | `Lead` y escritura de la fusión | Base en 002 plan:107-116; `Lead`, `por_id_fiscal` y `aplicar_fusion` en spec 003 §Puertos y en este plan (Diseño → Dedup) |
| P8 | `FuenteNoDisponible` y aislamiento | 002 plan:99 (la define) y :295 (`EjecutarBusqueda` aísla por fuente) |
| P9 | `CHECK` de `costos.tipo` | 002 plan:210 (ya incluye `overpass_query`; la `0003` no toca `costos`) |
| P10 | Tarifas en `Decimal` | 002 plan:150 (`Decimal(str(v))`, nunca `float`) |
| P11 | `sin_fuente_para` y selección | 002 plan:101 (`cubre`) y :298 (la traducción de criterios es de la 003); tipo de retorno en spec 003 §Flujo, paso 2: `sin_fuente_para` = `seleccionadas` vacío, derivado en `EjecutarBusqueda` |

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
│   ├── modelos.py                      # + columnas de leads y revision_dedup (drift)
│   ├── cli.py                          # (del 002) + --ciudad, hosts y limitador para OSM, resumen por fuente
│   ├── seguridad/
│   │   ├── cifrado.py                  # Cifrador: AES-256-GCM + HMAC-SHA256, subclaves HKDF
│   │   └── catalogo_sensibles.py       # CIFRADAS: telefono_cifrado, email_cifrado, nombre_cifrado, direccion_cifrada; CONDICIONALES: nombre, direccion, nombre_normalizado
│   └── modulos/descubrimiento/
│       ├── dominio/
│       │   ├── modelos.py              # (del 002) + Geo, campos de EmpresaCruda y PaginaEmpresas, Lead, CambiosLead
│       │   ├── puertos.py              # (del 002) + métodos de RepositorioLeads
│       │   ├── normalizacion.py        # normalizar_nombre/ciudad/dominio, a_e164
│       │   ├── geo.py                  # haversine
│       │   ├── dedup.py                # resolver_duplicado, fusionar, clasificar_similitud, umbrales
│       │   └── seleccion.py            # seleccionar_fuentes
│       ├── aplicacion/
│       │   ├── registro.py             # (del 002) + cargar_actividades, cargar_hosts_compartidos
│       │   └── ejecutar_busqueda.py    # (del 002) selección + normaliza + dedup + resumen por fuente
│       └── infraestructura/
│           ├── adaptadores/
│           │   ├── __init__.py         # catálogo + osm_overpass
│           │   ├── osm_overpass.py
│           │   └── croma_supersociedades.py   # + geo; canales en None
│           └── persistencia/
│               └── repositorio_leads.py       # + métodos nuevos; cifra/hashea
└── tests/
    ├── unit/seguridad/test_cifrador.py
    ├── unit/descubrimiento/{test_normalizacion,test_seleccion_fuentes,test_dedup,test_osm_overpass}.py
    ├── unit/descubrimiento/{test_registro,test_croma_supersociedades}.py   # del 002, se actualizan
    ├── contratos/fabricas.py                                               # del 002, + fábrica osm_overpass
    ├── fixtures/osm/                                                       # respuestas Overpass sintéticas
    ├── integration/{test_dedup_repo,test_busqueda_dos_fuentes}.py
    ├── integration/{test_costos_repo,test_rls}.py                          # del 002, + casos
    └── arquitectura/{test_cifrado,test_migraciones}.py                     # test_migraciones del 002, + pg_trgm
supabase/migrations/0003_leads_cifrado_nombre_direccion.sql   # DDL propuesto abajo; pendiente de aprobación
supabase/migrations/0003_osm_dedup.sql   # el número cambia: 0003 es del cifrado y la 005 toma la 0004; osm_dedup toma el siguiente libre
docs/arquitectura-backend.md
```

**Structure Decision**: todo dentro del módulo `descubrimiento` del 002, salvo `app/seguridad/`, que la spec pone fuera porque la reusan el 006 y el 007. `test_fuente_descubrimiento.py` no se toca. Ningún archivo nuevo en `persistencia/` (los `EXCLUIDOS` del 002 siguen valiendo).

## Diseño, punto por punto

**Registro y selección.** `osm_overpass` ya está en `fuentes.yaml` con `habilitado: true`, `paises: [CO, MX, PE, BR, "*"]`, `filtros: [ciudad, tipo_negocio]` y `licencia: ODbL`; el slice lo agrega al catálogo y `sin_implementacion` pasa a `{"croma_dian_trade_co"}`. `seleccionar_fuentes(metas: Iterable[MetaFuente], criterios, actividades)` (pura) lee `paises`/`filtros` y aplica país (con `cubre()`, que pierde la parte de filtros) → actividad → geografía; devuelve `(seleccionadas, ignoradas)`. No recibe `Registro`: es de `aplicacion` y el contrato `layers` (002 plan:31) no deja que el dominio lo importe. `EjecutarBusqueda` le pasa `[m for _, m in registro.fuentes]`, reemplaza el `cubre()` estricto por esta función y deriva `sin_fuente_para` de `seleccionadas` vacío. `Registro.fuentes` solo trae fuentes habilitadas e implementadas (002 plan:144-146): con el `fuentes.yaml` real, para BR y PE queda `seleccionadas == {osm_overpass}` e `ignoradas == {croma_supersociedades_co: "pais"}`. BR y PE van en un solo test parametrizado.

**Adaptador OSM.** Constructor como el de Croma (002 plan:150): `meta`, `RegistroCostos`, transporte, `costo_unitario`, `lote_id`, más `hosts_compartidos: frozenset`, reloj, `sleep` y `url` (constante con override `overpass_url` de `Settings`). Valida criterios contra `meta.filtros` antes de cualquier request. Query única con unión de etiquetas, `[out:json][timeout:25]`, área ciudad dentro del país, tope 500. User-Agent identificable desde config. Limitador por proceso (`# ponytail:` contador compartido con varios workers). Un reintento ante 429/504: `Retry-After` con tope 10 s; sin él, `max(1, limitador)`. Una fila `overpass_query` **por intento**, con los segundos del request, escrita antes de devolver o de lanzar. `FuenteNoDisponible` sin el cuerpo de la respuesta. El mapeo usa `normalizar_dominio` y `a_e164` del dominio; el `wa.me` va a `telefono` con `whatsapp_osm` solo si no hay otro válido, nunca a `web`. Devuelve `PaginaEmpresas(empresas, total=None, truncado, descartados_sin_nombre)`.

**Croma (del 002).** Solo suma `geo` desde `lat/lon` de la fixture y deja `telefono`, `email` y sus canales en `None`.

**Dedup.** `resolver_duplicado` en dominio, con el repositorio por puerto: regla 1 `por_id_fiscal` → 2 `por_dominio` (sin hosts compartidos) → 3 `por_telefono` (HMAC del E.164) → 4 `candidatos_por_nombre` (nombre + ciudad normalizados, similitud de `pg_trgm`). Veto por `id_fiscal` distinto en cualquier regla, que excluye y sigue. Desempate en dominio: reglas 1–3 por `creado_en` asc; regla 4 por similitud desc y `creado_en` asc, buscando el primero fusionable (≥ 0,92, geo en los dos, ≤ 250 m) antes de caer a revisión. Resultado:
- **fusionar:** `fusionar(lead, empresa) -> CambiosLead` (puro: nulos a completar, pares dato+canal que suben por confianza, `tipo_titular` si sube) → `aplicar_fusion(lead.id, cambios)` (UPDATE con `coalesce` en los simples; un par que viene en `CambiosLead` reemplaza dato, hmac y canal juntos, sin `coalesce`) → `agregar_lead_fuente` del 002. `cumplimiento` intacto.
- **revisar:** `obtener_o_crear_lead` del 002 (lead nuevo + su `cumplimiento`) → `registrar_revision(busqueda_id, lead_a, lead_b, similitud)`, con el par ordenado.
- **nuevo:** `obtener_o_crear_lead` como en el 002.

**Cifrado.** `Cifrador` con dos subclaves HKDF de `CIFRADO_KEY`: AES-256-GCM (nonce de 12 bytes como prefijo, AAD `tabla.columna`) y HMAC-SHA256 del E.164. El repositorio cifra y hashea al escribir (en `obtener_o_crear_lead` y en `aplicar_fusion`) y descifra al leer `Lead`; el dominio nunca ve bytes. Nada de contacto, nombre ni dirección de un no jurídico en logs, tampoco en `httpx` ni en mensajes de error.

**Nombre y dirección de no jurídicos (enmienda 2026-10-18).** `obtener_o_crear_lead` elige columnas por `tipo_titular`: `juridica` → `nombre`/`direccion`/`nombre_normalizado` en claro; otro → `nombre_cifrado`/`direccion_cifrada` y los tres en `NULL`. `aplicar_fusion` pasa de cifrado a claro en el mismo `UPDATE` cuando el tipo sube a `juridica` (el `CHECK` lo exige). `candidatos_por_nombre` une dos fuentes: `pg_trgm` sobre jurídicos y, para no jurídicos de la misma `ciudad_normalizada` (tope 2000), descifra + `normalizar_nombre` + `similitud_trigramas` (función pura de `dominio/normalizacion.py`, misma definición que `pg_trgm`; test de equivalencia contra Postgres). Dedup de OSM contra OSM: teléfono (HMAC) y dominio. La lectura para el tablero pasa solo por el repositorio.

**Migración de `nombre`/`direccion` cifrados** (a mano, `0003`; DDL propuesto al final de este archivo, sin escribir hasta el OK del dueño): columnas `nombre_cifrado`/`direccion_cifrada`, `nombre` nullable, dos `CHECK` por `tipo_titular` (`NOT VALID` hasta el backfill T056). Sin tabla nueva, sin `GRANT` nuevo.

**Migración `0003`** (a mano; suma `CHECK (tipo_titular = 'juridica' OR nombre_normalizado IS NULL)`): `CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions`; columnas nuevas de `leads` con los `CHECK` de canal y de dato ⇔ canal; GIN con `extensions.gin_trgm_ops`; btree no únicos `(tenant_id, dominio)` y `(tenant_id, telefono_hmac)`; `revision_dedup` con RLS, `CHECK (lead_a < lead_b)`, `UNIQUE (lead_a, lead_b)` y `GRANT` a `app_rt`. No toca `costos`.

**Costos y cumplimiento.** La única operación de salida nueva es el `POST` a Overpass, y siempre deja su fila. Cumplimiento por lead OSM nuevo: `fuente='osm_overpass'`, `licencia=meta.licencia`, `url_origen` del elemento, `as_of` de la base OSM, `base_legal` nula hasta el 007. Este slice no contacta a nadie: el chequeo de envío (`tipo_titular == 'juridica'`, canal publicado, fila en `cumplimiento`) no se ejercita; deja los datos para que el 006/007 lo evalúen.

## Orden de tareas (TDD)

> El orden de ejecución que vale es el de `tasks.md`: primero las tareas [MIN] y después la Fase Pulido. Lo que sigue es el orden por pasos de la spec, y sirve de referencia para el contenido de cada paso.

El de la spec (§Plan de tareas), con la puerta del 002 adelante:

0. **Puerta:** el 002 mergeado en `main` y esta rama al día con `main`.
1. Normalización, `geo.py` y `dedup.yaml`.
2. Selección de fuentes y `actividades.yaml`.
3. `Cifrador` y `ConfigInvalida`.
4. Migración `0003` (pg_trgm → RLS → `CHECK` → cifrado de catálogo). Advisor revisa RLS y cifrado.
5. Dedup y fusión en dominio. Advisor revisa los tests.
6. Repositorio contra `pg_trgm` real.
7. Adaptador OSM y su test de costos en integración. Advisor revisa los tests de costos.
8. Catálogo + fábrica de contrato y `test_registro.py`.
9. `EjecutarBusqueda` con dos fuentes y test de logs.
10. CLI y una corrida real contra Overpass, avisada antes.
11. `docs/arquitectura-backend.md`.

Los pasos 1, 2 y 3 son independientes entre sí. Los cortes son los de la spec (§Cuándo cortar), en ese orden.

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| Sin `research.md`, `data-model.md`, `contracts/`, `quickstart.md` | La spec ya trae las decisiones, las tablas y los tests; esos archivos la duplicarían | Generar los cuatro archivos repitiendo la spec |
| Descifrar nombres de no jurídicos para la regla 4 (en vez de HMAC del nombre) | Mantiene la similitud difusa y que el resultado no dependa del orden de las fuentes; el costo es lineal por ciudad | HMAC del nombre normalizado: solo igualdad exacta, pierde los plurales y cercanos; queda como `# ponytail:` |
| `phonenumbers` en `dominio/` | La normalización E.164 es regla de dominio y la librería es pura, sin I/O; la spec lo decide así | Mover `a_e164` a infraestructura: el dedup y el adaptador tendrían dos normalizaciones |
| `PaginaEmpresas` suma dos campos | `truncado` y `descartados_sin_nombre` son por página y por fuente; con default, Croma y la suite no cambian | Un canal lateral (atributo del adaptador) que el orquestador lee después de `buscar`: estado mutable fuera del puerto |
| `test_todo_adaptador_de_registro_esta_declarado` en rojo de T038 a T048 | La clase existe desde T038 y entra al catálogo recién cuando la fábrica de contrato puede pasar los tres tests | Meterla al catálogo en T038: `test_hay_fabrica…` y la suite quedarían rojas igual, con menos señal |
| `test_icp_fuera_de_colombia_solo_usa_osm` parametrizado sobre BR y PE | El pedido del slice dice "en BR y PE la única fuente es OSM"; la spec original solo probaba BR | Un test aparte para PE que repite el de BR |
| `cubre()` pierde la parte de filtros y `test_cubre` del 002 cambia | Con la selección, un filtro que la fuente no declara se descarta en vez de excluir la fuente; mantener el chequeo estricto en `cubre` contradice la selección | Dejar `cubre` estricto sin usarlo: código muerto con un test que afirma lo contrario de lo que hace el orquestador |
| Doc (X) es el primer corte | Lo fija la spec; el 013 la consolida | — |

## DDL propuesto, pendiente de aprobación del dueño

> **No es un archivo todavía.** Se crea en `supabase/migrations/` solo con el OK explícito del dueño. Una migración propia, independiente de la `0003_osm_dedup.sql` (no usa ninguna de sus columnas), para que entre en el [MIN]. Número asignado por el coordinador: `0003_leads_cifrado_nombre_direccion.sql`; la 005 toma la `0004`. La migración de osm_dedup, que esta spec llama `0003_osm_dedup.sql`, se renumera al siguiente libre en su PR (`migrar_local.sh` rechaza versiones repetidas).

```sql
-- 0003: nombre y dirección cifrados para titulares no jurídicos. SQL a mano. Corre como postgres (dueño).
-- Jurídica: nombre y direccion en claro. Cualquier otro tipo_titular: solo nombre_cifrado / direccion_cifrada.
-- El cifrado lo hace la app (AES-GCM, CIFRADO_KEY); SQL no cifra nada.

ALTER TABLE public.leads
  ADD COLUMN nombre_cifrado    bytea,
  ADD COLUMN direccion_cifrada bytea;

-- Un lead no jurídico no tiene nombre en claro.
ALTER TABLE public.leads ALTER COLUMN nombre DROP NOT NULL;

-- NOT VALID: las filas ya guardadas (leads OSM del [MIN], en claro) no se pueden cifrar desde SQL.
-- Las filas nuevas y las modificadas sí se validan. Se valida (VALIDATE CONSTRAINT) cuando el script
-- de la app (tarea T056) las haya cifrado; en una base vacía no hay nada que validar.
ALTER TABLE public.leads
  ADD CONSTRAINT leads_nombre_segun_titular_ck CHECK (
    (tipo_titular =  'juridica' AND nombre IS NOT NULL AND nombre_cifrado IS NULL)
    OR
    (tipo_titular <> 'juridica' AND nombre IS NULL AND nombre_cifrado IS NOT NULL)
  ) NOT VALID,
  ADD CONSTRAINT leads_direccion_segun_titular_ck CHECK (
    (tipo_titular =  'juridica' AND direccion_cifrada IS NULL)
    OR
    (tipo_titular <> 'juridica' AND direccion IS NULL)
  ) NOT VALID;

-- Sin GRANT nuevo: app_rt ya tiene SELECT, INSERT, UPDATE, DELETE sobre public.leads (0002) y los
-- GRANT de tabla cubren las columnas nuevas. Sin REVOKE: anon/authenticated ya no tienen nada en public
-- y no hay default privileges para columnas. RLS no cambia: leads ya tiene ENABLE ROW LEVEL SECURITY y
-- la política tenant_aislado (0002); no hay tabla nueva.
```

Puntos para la aprobación:
- **Idempotencia y "dos veces desde vacío":** `migrar_local.sh` registra cada versión en `supabase_migrations.schema_migrations` y salta la ya aplicada, igual que `supabase db push`, así que la segunda corrida no reaplica nada (el `ADD COLUMN`/`ADD CONSTRAINT` sin `IF NOT EXISTS` no se ejecuta dos veces). Desde vacío corre después de la `0002` y no depende de la migración de osm_dedup; `test_migraciones.py::test_migrar_local_desde_vacio_dos_veces_sin_drift` ya cubre la doble corrida y el drift (por eso `app/modelos.py` se actualiza en la misma tarea). Verificar: tras el verde, `migrar_local.sh` dos veces sobre base vacía, la segunda sin "aplicada".
- **`leads.nombre text NOT NULL` → nullable:** necesario para guardar un no jurídico sin nombre en claro. El `CHECK` devuelve la garantía: una jurídica no puede quedar sin nombre. `app/modelos.py` pasa `nombre` a `nullable=True` y suma las dos columnas para que el drift check quede vacío.
- **`NOT VALID` y filas existentes:** decisión del dueño. Alternativa si hoy no hay datos que importen (solo dummy): `ADD CONSTRAINT ...` sin `NOT VALID` y vaciar `leads` de las pruebas; se pierde el backfill (T056) y el `VALIDATE`.
- **`osm_dedup` suma después** `CHECK (tipo_titular = 'juridica' OR nombre_normalizado IS NULL)` en su migración (el `nombre_normalizado` de un no jurídico sería el nombre en claro con otro formato).
- **Otras tablas:** `revision_dedup` guarda ids y similitud, no nombres; `lead_fuentes.url_origen` y `cumplimiento.url_origen` son la URL del elemento OSM (no llevan el nombre).
