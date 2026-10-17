# Implementation Plan: 002 — Puertos, registro de adaptadores y Supersociedades

**Branch**: `feature/002-puertos-registro-supersociedades` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Este plan cierra el puerto `FuenteDescubrimiento` tal como lo fija la spec; no lo rediseña. Lo que la spec no decide está en **Preguntas abiertas**, cada una con el default aprobado por el dueño. De este puerto cuelgan la 003 (`osm_overpass`), la 006 (reusa `MetaFuente`, el registro y `RegistroCostos`) y la 011 (`datos_gov_co_rues`).
>
> Artefactos: por pedido explícito este slice entrega solo `plan.md` y `tasks.md`. Lo que `/speckit-plan` pondría en `research.md`, `data-model.md`, `contracts/` y `quickstart.md` va resumido acá (secciones Puerto, Datos, Contrato y Validación).

## Summary

Primer módulo de negocio, `descubrimiento`, más el módulo `costos` que es dueño del libro. Entrega el puerto `FuenteDescubrimiento`, la carga de la sección `fuentes_descubrimiento` de `config/fuentes.yaml`, la suite de contrato parametrizada sobre el catálogo y el adaptador `croma_supersociedades_co`. Una búsqueda por CLI (país + CIIU + departamento) deja filas en `busquedas`, `leads`, `lead_fuentes`, `cumplimiento` y `costos`, deduplicadas por `(pais, id_fiscal)`. La migración `0002` crea las tablas con RLS y cierra `anon`/`authenticated`. Sin IA, sin endpoint HTTP, sin columnas sensibles.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI (sin cambios), SQLAlchemy 2 Core + psycopg 3, pydantic-settings. **Cambian:** `httpx` sale del grupo dev a `dependencies` (lo usa el adaptador); `pyyaml` entra en `dependencies` (no está en `uv.lock`). La 004 y la 012 declaran la misma línea de `pyyaml`: el choque se resuelve en el merge que venga después.
**Storage**: Postgres (Supabase en prod; `postgres:16` en CI). Migración a mano `supabase/migrations/0002_descubrimiento.sql`.
**Testing**: pytest; `httpx.MockTransport` para Croma; import-linter (`layers` + el `forbidden` del 001).
**Target Platform**: CLI local (`uv run python -m app.cli buscar …`); la API no expone nada nuevo.
**Project Type**: web app (solo toca `backend/`).
**Performance Goals**: N/A.
**Constraints**: ≤ 4 h. Croma ~100 requests/24 h y 1.500 créditos/mes: los tests no tocan la red, una sola corrida real (tarea de CLI), avisada. `api` entra por el pooler en modo transacción: ninguna llamada HTTP corre dentro de una transacción abierta.
**Scale/Scope**: 2 módulos (`descubrimiento`, `costos`), 1 puerto de fuente, 1 adaptador, 7 tablas, 1 comando de CLI.

## Constitution Check

*GATE: antes de Phase 0 y re-chequeado tras Phase 1.*

| Principio | Qué entrega este slice | Estado |
|---|---|---|
| I Hexagonal | Contrato `layers` (`infraestructura > aplicacion > dominio`) con **todos** los containers de `app.modulos.*` (hoy `descubrimiento` y `costos`), con canario. Contrato `forbidden` `app.modulos.descubrimiento` ↛ `app.modulos.costos.infraestructura`, con canario: `app.cli` es la única raíz que los une. Puertos como `Protocol` en `dominio/`. Catálogo `clave → clase` solo en `infraestructura/adaptadores/__init__.py`. Suite de contrato en `tests/contratos/`. Test de que todo adaptador está declarado. | ✅ |
| II Test primero | Cada tarea arranca en rojo por la razón correcta (mutación donde el rojo natural sería `UndefinedTable`; ver `tasks.md`). El advisor revisa RLS, privilegios, costos y dedup antes de aceptarlos. Marca "src sin tests" del 001: sigue diferida (ver Complexity). | ⚠️ |
| III Tenant/RLS | Todas las tablas con `tenant_id` + RLS `USING/WITH CHECK`; `tenants` por `id`. Unidad de trabajo con `set_config('app.tenant_id', …, true)` como primera sentencia. `test_tenant_b_no_accede_a_datos_de_a[tabla]`, `test_privilegios_supabase.py` (con `supabase_simulado.sql`) y `test_tenant_no_sobrevive_al_commit`. `fuente_cache` sin tenant, justificada. | ✅ |
| IV Migraciones | `0002` a mano. `test_migrar_local_desde_vacio_dos_veces_sin_drift` pasa a comparar contra las versiones de `supabase/migrations/*.sql`. `app/modelos.py` declara las 7 tablas con restricciones, índices, FKs y tipos exactos para que el drift check siga vacío. | ✅ |
| V Seguridad | `CROMA_API_KEY` por `Settings` (entorno), nunca en logs, en el body ni en el hash del caché. `sembrar_tenant.py` pide la URL de `postgres` por `getpass`, con test de que no la imprime. | ✅ |
| VI Contacto cifrado | N/A: NIT, razón social y dirección de una persona jurídica no son dato personal. Teléfono y correo no entran en este slice. | — |
| VII Cumplimiento | `tipo_titular` NOT NULL (default `desconocido`); Supersociedades → `juridica`, con test de que sobrevive al guardado. Fila en `cumplimiento` por lead nuevo, en la **misma transacción** que el lead, con test de rollback. | ✅ |
| VIII Costos | Una fila en `costos` por intento HTTP, escrita antes de que `buscar` retorne o lance. `test_costos_por_adaptador` exige `RegistroCostos` en el constructor. Integración contra Postgres real. | ✅ |
| IX Evals | N/A (sin IA). | — |
| X Doc viva | `docs/arquitectura-backend.md`: módulos, puerto, registro, cómo agregar un adaptador (ver pregunta abierta 12). | ⚠️ |

Re-chequeo post-diseño: sin violaciones nuevas.

## Puerto `FuenteDescubrimiento` (lo que cuelga de acá)

Todo en `backend/app/modulos/descubrimiento/dominio/`, sin framework.

```python
class Actividad(NamedTuple):          # NamedTuple: el test compara con ("4711", "CIIU")
    codigo: str
    sistema: str                      # "CIIU" | "SCIAN" | "CNAE"

TipoTitular = Literal["juridica", "natural", "desconocido"]

@dataclass(frozen=True)
class CriteriosICP:
    pais: str                         # ISO 3166-1 alfa-2, mayúsculas
    filtros: Mapping[str, str | tuple[str, ...]]   # claves del vocabulario de fuentes.yaml: ciiu, departamento, …; tupla = varios valores

@dataclass(frozen=True)
class EmpresaCruda:
    pais: str
    nombre: str
    fuente: str                       # clave del registro, p. ej. "croma_supersociedades_co"
    url_origen: str                   # sin query string ni API key
    as_of: datetime                   # UTC
    actividad: Actividad
    id_fiscal: str | None = None      # solo dígitos, sin DV (normalizar_nit)
    tipo_titular: TipoTitular = "desconocido"
    ciudad: str | None = None
    direccion: str | None = None
    web: str | None = None

@dataclass(frozen=True)
class PaginaEmpresas:
    empresas: tuple[EmpresaCruda, ...]
    total: int | None                 # lo que reporte la fuente; lo usa la vista previa del 005

@dataclass(frozen=True)
class MetaFuente:                     # se arma desde la entrada de fuentes.yaml, no desde la clase
    clave: str
    proveedor: str
    paises: frozenset[str]            # "*" = cualquiera
    filtros: frozenset[str]
    trae: frozenset[str]
    tipo: Literal["dataset", "live"]
    licencia: str
    endpoint: str | None = None
    tipo_titular_implicito: TipoTitular | None = None

class FuenteDescubrimiento(Protocol):
    meta: MetaFuente
    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas: ...
```

**Qué recibe:** `CriteriosICP` + `pagina` (este slice solo usa 1). **Qué devuelve:** `PaginaEmpresas` con `EmpresaCruda` ya normalizadas (rastreado en spec.md, Decisiones técnicas). **Qué lanza:**
- `CriterioNoSoportado`: alguna clave de `criterios.filtros` no está en `meta.filtros`. Se lanza antes de cualquier request.
- `LimiteFuenteAgotado`: el contador de 24 h llegó al límite antes de un intento, o Croma respondió 429 (sin reintento).
- `FuenteNoDisponible`: los intentos fallaron (5xx/timeout tras el reintento, o 4xx distinto de 429). Las filas de `costos` ya quedaron escritas.

Funciones de dominio: `normalizar_nit(texto) -> str` y `cubre(meta, criterios) -> bool` (`pais ∈ paises` o `"*" ∈ paises`, y `set(filtros) ⊆ meta.filtros`).

**Lo que los slices siguientes agregan sin tocar la firma:** campos opcionales con default `None` en `EmpresaCruda` (la 003 suma `telefono`, `email`, `geo`, `telefono_canal` y `email_canal`, ver 003 spec.md:25 y :87-92; el cifrado al persistir es de la 003/006); nuevas claves en el catálogo y en `fuentes.yaml` (003, 011). Un cambio a `buscar` o a los tipos de retorno es cambio de puerto y pide spec.

`RepositorioLeads` (Protocol en `descubrimiento/dominio/`):

```python
class RepositorioLeads(Protocol):
    def crear_busqueda(self, criterios: CriteriosICP) -> UUID: ...
        # transacción propia, confirmada ANTES de llamar a los adaptadores
    def obtener_o_crear_lead(self, e: EmpresaCruda, licencia: str) -> tuple[UUID, bool]: ...
        # (id, nuevo). Si es nuevo inserta lead + cumplimiento en UNA transacción
    def agregar_lead_fuente(self, lead_id: UUID, busqueda_id: UUID, e: EmpresaCruda, licencia: str) -> None: ...
        # ON CONFLICT DO NOTHING
    def cerrar_busqueda(self, busqueda_id: UUID, estado: str) -> None: ...
```

`OperacionCosto` y `RegistroCostos` viven en `backend/app/modulos/costos/dominio/` (el módulo `costos` es su dueño; la 005, 006, 007 y 008 lo importan de ahí):

```python
@dataclass(frozen=True)
class OperacionCosto:                 # skill libro-costos + `gratis`
    tipo: str                         # "croma_consulta" en este slice
    unidades: Decimal
    costo_unitario: Decimal
    moneda: str                       # "USD"
    proveedor: str
    fuente: str | None
    canal: str | None
    lead_id: UUID | None
    lote_id: UUID | None
    gratis: bool
    ts: datetime | None = None        # None = now() de la base

class RegistroCostos(Protocol):
    def registrar(self, op: OperacionCosto) -> None: ...
    def requests_24h(self, proveedor: str) -> int: ...
    def creditos_mes(self, proveedor: str) -> Decimal: ...
```

## Registro: `config/fuentes.yaml`

- `cargar_registro(ruta_yaml, catalogo) -> Registro` en `descubrimiento/aplicacion/`. Lee **solo** `fuentes_descubrimiento`.
  - Entradas con `habilitado: false`: se ignoran y no se validan.
  - Entradas con `habilitado: true` sin `paises` o sin `filtros`: `RegistroInvalido`.
  - Habilitadas con clave en el catálogo: van a `Registro.fuentes` como `(clase, MetaFuente)`.
  - Habilitadas sin clave en el catálogo: van a `Registro.sin_implementacion` (hoy `{"croma_dian_trade_co", "osm_overpass"}`); no rompen.
  - Clave del catálogo ausente del YAML: `RegistroInvalido`.
- `catalogo = {"croma_supersociedades_co": CromaSupersociedades}` en `descubrimiento/infraestructura/adaptadores/__init__.py`. Es el único lugar que nombra clases concretas.
- La raíz de composición es `app/cli.py`: lee `fuentes.yaml` (registro y `limites`) y `tarifas.yaml` (cada tarifa como `Decimal(str(v))`, nunca `float`), construye cada adaptador con `meta`, `RegistroCostos`, transporte `httpx`, caché, tarifa resuelta, límites, API key y `lote_id`, y le pasa a `EjecutarBusqueda` instancias ya armadas.
- Conectar o desconectar una fuente: `habilitado: true/false` en el YAML. Sumar una fuente: clase + clave en el catálogo + entrada en el YAML + fábrica en la suite de contrato.

## Suite de contrato

`backend/tests/contratos/test_fuente_descubrimiento.py`, parametrizada sobre `catalogo` (no sobre una lista escrita a mano). Cada adaptador se construye con transporte falso y `RegistroCostos` falso por una fábrica en `backend/tests/contratos/fabricas.py` (`clave → fabrica(transporte, registro)`, con su respuesta sintética).

- Guardas contra colección vacía: `assert catalogo` a nivel de módulo, y `::test_hay_fabrica_para_cada_clave_del_catalogo` (sin esto, un adaptador nuevo sin fábrica dejaría la suite verde sin correr).
- `::test_devuelve_empresas_normalizadas[clave]`: cada empresa trae `pais`, `nombre`, `fuente == clave`, `url_origen`, `as_of` con zona, y `actividad.sistema`. Rojo: una fábrica cuyo `as_of` no tiene zona o cuya `fuente` difiere de la clave.
- `::test_registra_costo_antes_de_devolver[clave]`: una fila por intento HTTP en el falso cuando `buscar` retorna. Rojo: un adaptador falso que no llama a `registrar`.
- `::test_rechaza_criterio_no_soportado[clave]`: la clave centinela `"__criterio_inexistente__"` (ninguna fuente real la soporta, a diferencia de una clave real que otra fuente sí podría tener) lanza `CriterioNoSoportado` y el transporte recibe 0 requests. Rojo: un adaptador que hace el request antes de validar.

La 003 y la 011 entran a esta suite agregando su clave y su fábrica; no escriben tests de contrato propios.

## Transacciones (pooler en modo transacción)

Orden de una corrida, y en qué transacción va cada cosa:
1. `crear_busqueda`: transacción propia, **confirmada** antes de llamar a cualquier adaptador.
2. `adaptador.buscar(...)`: el HTTP corre **sin** transacción abierta. Cada `RegistroCostos.registrar` y cada upsert de `fuente_cache` abre y confirma su propia transacción corta (con su `set_config` del tenant donde aplica). Un fallo posterior no borra el gasto.
3. Por cada `EmpresaCruda`: `obtener_o_crear_lead` (lead + `cumplimiento` si es nuevo, en una transacción) y `agregar_lead_fuente`.
4. `cerrar_busqueda` con su `estado`.

## Dónde escribe en `costos` y en `cumplimiento`

| Qué | Quién | Cuándo | Transacción |
|---|---|---|---|
| `costos`: 1 fila por intento HTTP enviado, `tipo='croma_consulta'`, `proveedor='croma'`, `fuente=<clave>`, `lead_id=None`, `lote_id=<busqueda_id>` | el adaptador, vía `RegistroCostos.registrar` | después de cada respuesta o timeout, antes de devolver o de lanzar | propia y corta |
| `costos` en hit de caché | nadie | — | — |
| `cumplimiento`: 1 fila por lead **nuevo** (`fuente`, `licencia`, `url_origen`, `as_of`, `base_legal=NULL`) | `RepositorioLeads.obtener_o_crear_lead`, llamado por `EjecutarBusqueda` | al insertar el lead | la misma que el lead: si falla el `cumplimiento`, no queda el lead |
| `lead_fuentes`: 1 por `(lead, fuente, busqueda)` | `EjecutarBusqueda` | siempre, nuevo o existente | corta, `ON CONFLICT DO NOTHING` |

Valores de la fila de `costos`:
- 200: `unidades=1` (dataset), `costo_unitario = tarifas.croma.usd_por_credito`.
- 5xx, 429, otro 4xx o timeout: `unidades=0`, `costo_unitario=0`. Cuenta para el límite de 24 h.
- `gratis = creditos_mes("croma") < limites.croma_creditos_gratis_mes`, leído antes del intento.

## Límite de Croma y caché

Orden dentro de `buscar`:
1. Validar criterios (`CriterioNoSoportado`).
2. Armar el body: filtros de dominio → nombres de Croma (`ciiu` → `ciiu_code`, `departamento` → `department`), `per_page=100`, `page=pagina`. La API key va solo en el header, nunca en el body ni en el hash.
3. Caché: `hash_params = sha256(json.dumps(body, sort_keys=True))` sobre `(proveedor, endpoint, hash_params)`. Hay hit: devuelve desde `respuesta`, con su `as_of`, sin request y sin fila en `costos`.
4. Antes de **cada** intento: si `requests_24h("croma") >= limites.croma_requests_por_24h`, `LimiteFuenteAgotado`. Con 99 previas, un 502 deja 100 y el reintento no se hace.
5. Request con timeout 10 s. Ante 502, 503 o timeout, un reintento con backoff. 429: `LimiteFuenteAgotado` sin reintento. Otro 4xx: `FuenteNoDisponible` sin reintento. Cada intento escribe su fila.
6. Solo en 200: upsert en `fuente_cache` y mapeo a `EmpresaCruda`. Ni 4xx ni 5xx se cachean.

Contadores en `costos/infraestructura/postgres_costos.py`, sobre `costos` filtrado por `proveedor`:
- `requests_24h`: `COUNT(*)` con `ts > now() - interval '24 hours'`.
- `creditos_mes`: `SUM(unidades)` con `ts >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'`.
- `# ponytail:` cuentan por tenant (RLS). Con un tenant coincide con la cuenta de Croma; con varios, contador global.

`fuente_cache` es global (sin `tenant_id`, sin RLS), UNIQUE `(proveedor, endpoint, hash_params)`, `GRANT SELECT, INSERT, UPDATE` a `app_rt`. Sin TTL en este slice. No se expone por API: Croma no se redistribuye.

## Datos (migración `0002_descubrimiento.sql`)

Las tablas y restricciones son las de la spec (sección Decisiones técnicas). Lo que el plan agrega:
- `id uuid PRIMARY KEY DEFAULT gen_random_uuid()` en todas; `tenant_id uuid NOT NULL REFERENCES tenants(id)`.
- FKs: `lead_fuentes.lead_id`, `lead_fuentes.busqueda_id`, `cumplimiento.lead_id` → `leads`/`busquedas`. `costos.lead_id` y `costos.lote_id` sin FK: un costo no se pierde porque se borre un lead.
- `busquedas.estado text NOT NULL DEFAULT 'creada' CHECK (estado IN ('creada','terminada','con_errores'))`.
- `costos.ts timestamptz NOT NULL DEFAULT now()`, índice `(tenant_id, proveedor, ts)` para los contadores.
- `costos.tipo text NOT NULL CHECK (tipo IN ('socrata_descarga','overpass_query','web_fetch','llm_tokens_in','llm_tokens_out','jev_tokens','croma_consulta','email_envio','whatsapp_plantilla','dapta_llamada','minutos_humanos'))`: la lista cerrada de la skill `libro-costos`. Un tipo nuevo es una migración, no un string libre.
- Choque conocido con la 003: `leads.idioma_contacto` y `fuente_cache.respuesta` caen en el patrón de `test_ninguna_columna_de_contacto_fuera_del_catalogo` de la 003. Lo resuelve la 003 sumándolas a su lista cerrada; acá no se renombran.
- `GRANT` a `app_rt`: `SELECT, INSERT, UPDATE, DELETE` en las tablas de tenant; `SELECT` en `tenants`; `SELECT, INSERT, UPDATE` en `fuente_cache`.
- Al final, el bloque `DO` de `REVOKE` a `anon`/`authenticated` (solo si existen en `pg_roles`). El escenario sin esos roles ya lo cubre el fixture `base_vacia` de `test_migraciones.py` (vanilla, sin `supabase_simulado.sql`).
- `backend/app/modelos.py` declara las 7 tablas en SQLAlchemy Core con lo que `compare_metadata` compara:
  - tipos exactos: `UUID`, `JSONB`, `DateTime(timezone=True)`, `Numeric`, `Boolean`, `Text`;
  - `UniqueConstraint` `(tenant_id, pais, id_fiscal)` en `leads`, `(lead_id, fuente, busqueda_id)` en `lead_fuentes`, `(lead_id)` en `cumplimiento`, `(proveedor, endpoint, hash_params)` en `fuente_cache`;
  - `Index` `(tenant_id, proveedor, ts)` en `costos`;
  - todas las `ForeignKey`;
  - `idioma_contacto` con `Computed(..., persisted=True)`. Si Alembic igual reporta diferencia en la columna generada o en los CHECK, se documenta y se ajusta el comparador, no la migración.

## Validación (lo que iría en quickstart.md)

```bash
cd backend && uv sync
psql "$ADMIN" -f scripts/roles.sql && psql "$ADMIN" -f scripts/supabase_simulado.sql
scripts/migrar_local.sh "$ADMIN"
uv run pytest -q && uv run lint-imports
uv run python scripts/sembrar_tenant.py                      # pide la URL por getpass, imprime el id
uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11
```

Salida esperada de la CLI: encontrados · únicos · nuevos · créditos gastados · `sin_implementacion`. La segunda corrida idéntica: 0 créditos (caché).

## Project Structure

### Documentation (this feature)

```text
specs/002-puertos-registro-supersociedades/
├── spec.md · plan.md · tasks.md
```

### Source Code

```text
backend/
├── pyproject.toml                      # contrato layers sobre app.modulos.*; httpx y pyyaml en dependencies
├── app/config.py                       # + croma_api_key: SecretStr | None
├── app/db.py                           # + unidad de trabajo con set_config(..., true)
├── app/modelos.py                      # 7 tablas en Core, con restricciones e índices (drift)
├── app/cli.py                          # raíz de composición: `buscar`
├── app/modulos/costos/
│   ├── dominio/{modelos.py, puertos.py}            # OperacionCosto, RegistroCostos
│   └── infraestructura/postgres_costos.py
├── app/modulos/descubrimiento/
│   ├── dominio/{modelos.py, puertos.py, nit.py, errores.py}
│   ├── aplicacion/{ejecutar_busqueda.py, registro.py}
│   └── infraestructura/
│       ├── adaptadores/{__init__.py, croma_supersociedades.py}
│       └── persistencia/{repositorio_leads.py, repositorio_cache.py}
├── scripts/{supabase_simulado.sql, sembrar_tenant.py}
└── tests/
    ├── arquitectura/{test_import_linter.py, test_registro_adaptadores.py, test_costos_por_adaptador.py, test_migraciones.py}
    ├── contratos/{fabricas.py, test_fuente_descubrimiento.py}
    ├── fixtures/croma_supersociedades_sintetica.json
    ├── unit/descubrimiento/{test_dominio.py, test_registro.py, test_croma_supersociedades.py, test_ejecutar_busqueda.py}
    ├── unit/test_cli.py
    └── integration/{test_leads_repo.py, test_costos_repo.py, test_rls.py, test_privilegios_supabase.py, test_sembrar_tenant.py}
supabase/migrations/0002_descubrimiento.sql
.github/workflows/ci.yml                # supabase_simulado.sql entre roles.sql y migrar_local.sh
.claude/skills/slice-tdd/SKILL.md       # slice/ → feature/ (lo pide la spec)
docs/arquitectura-backend.md
```

**Structure Decision**: módulos hexagonales según el principio I. `descubrimiento` importa `costos/dominio` (el puerto), nunca `costos/infraestructura`; lo garantiza el contrato `forbidden`, y solo `app.cli` une las dos. `costos` no tiene `aplicacion/` todavía: T005 prueba primero la capa opcional `"(aplicacion)"` en el import-linter instalado (`>=2.15` en `uv.lock`); si no anda, el respaldo es `costos/aplicacion/__init__.py` vacío hasta el 005. Este párrafo se corrige en T005 con lo que salga.

## Orden de tareas

El de la spec (pasos 1 a 9), detallado en [tasks.md](./tasks.md).

## Preguntas abiertas

Todas resueltas por el dueño con el default del plan, salvo donde se indica.

1. **Transacción de `costos`.** `postgres_costos.registrar` abre su propia transacción corta; lo mismo el upsert de `fuente_cache`. `crear_busqueda` también se confirma antes de llamar adaptadores. El HTTP nunca corre dentro de una transacción.
2. **`lote_id` y cómo llega al adaptador.** `lote_id = busqueda_id`, pasado al constructor; la CLI arma los adaptadores por búsqueda.
3. **Quién lee `limites`.** La CLI, y se los pasa al constructor; `cargar_registro` no cambia.
4. **Límite entre intentos.** Se chequea antes de cada intento. Con 99 previas, un 502 deja 100 y sale `LimiteFuenteAgotado`; la fila del 502 queda escrita, con su test.
5. **4xx.** *Cambiado por el dueño:* un 429 lanza `LimiteFuenteAgotado` sin reintento. Otro 4xx: sin reintento, fila con `unidades=0` y `costo_unitario=0`, y `FuenteNoDisponible`. Se verifica en la corrida real.
6. **TTL de `fuente_cache`.** Sin TTL en este slice; el `as_of` del caché viaja en la `EmpresaCruda`.
7. **`ts` de `costos`.** Lo pone la base (`DEFAULT now()`); `OperacionCosto.ts` queda opcional.
8. **NIT sin guion con DV pegado.** Solo se corta el DV si viene tras `-`. T006 suma el caso `"9001234567"` (queda igual). Se confirma con la forma real en la corrida.
9. **Formato de `departamento`.** Código DANE, mapeado a `department` en el adaptador; T026 lo aserta en el body. Se confirma en la corrida.
10. **`url_origen` y `as_of` de Croma.** `url_origen` = endpoint de `fuentes.yaml`, sin query ni key; `as_of` = momento de la respuesta, o el `as_of` del caché en un hit.
11. **Errores de una fuente en `EjecutarBusqueda`.** Captura `LimiteFuenteAgotado` y `FuenteNoDisponible` por fuente, sigue con las demás y los devuelve en el resultado; `busquedas.estado` queda `con_errores`. La `0002` pone CHECK sobre `estado` (`creada`, `terminada`, `con_errores`).
12. **`docs/arquitectura-backend.md` no existe.** Se crea acá con la sección de los módulos, y la 013 la consolida.
13. **Dónde vive `RegistroCostos`.** *Cambiado por el dueño:* se mueve ya a `app/modulos/costos/` (`dominio/` con `OperacionCosto` y `RegistroCostos`, `infraestructura/postgres_costos.py`). `EXCLUIDOS` de la spec, enmendado.
14. **Vocabulario de filtros entre fuentes.** `cubre()` estricto en este slice; la traducción de criterios es de la 003.
15. **`PaginaEmpresas` vs lista.** `PaginaEmpresas(empresas, total)`; rastreado en spec.md, Decisiones técnicas.

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| Marca "PR toca src sin tests" (II), sigue diferida | No entra en ≤ 4 h junto al primer módulo; lo cubre la revisión humana del PR | Meterla acá y recortar tests de RLS |
| `httpx` a runtime y `pyyaml` nuevo | El adaptador y el registro los necesitan en producción | `urllib` (sin `MockTransport`) o parsear YAML a mano |
| `fuente_cache` sin RLS | Datos públicos de gobierno, no del tenant; compartirla ahorra cupo de Croma | Caché por tenant: gasta el doble de un cupo de 100/día |
| Módulo `costos` con una sola pieza de infraestructura | La 005-008 lo importan; moverlo después tocaría cuatro slices | Dejarlo en `descubrimiento/dominio` y que otros módulos importen el dominio ajeno |
