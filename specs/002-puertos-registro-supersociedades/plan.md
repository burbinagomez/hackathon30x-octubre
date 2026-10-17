# Implementation Plan: 002 — Puertos, registro de adaptadores y Supersociedades

**Branch**: `feature/002-puertos-registro-supersociedades` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

> Este plan cierra el puerto `FuenteDescubrimiento` tal como lo fija la spec; no lo rediseña. Lo que la spec no decide está en **Preguntas abiertas**, cada una con el default que se usa si nadie responde antes de la tarea que la necesita. De este puerto cuelgan la 003 (`osm_overpass`), la 006 (reusa `MetaFuente`, el registro y `RegistroCostos`) y la 011 (`datos_gov_co_rues`).
>
> Artefactos: por pedido explícito este slice entrega solo `plan.md` y `tasks.md`. Lo que `/speckit-plan` pondría en `research.md`, `data-model.md`, `contracts/` y `quickstart.md` va resumido acá (secciones Puerto, Datos, Contrato y Validación).

## Summary

Primer módulo de negocio, `descubrimiento`: el puerto `FuenteDescubrimiento`, la carga de la sección `fuentes_descubrimiento` de `config/fuentes.yaml`, la suite de contrato parametrizada sobre el catálogo y el adaptador `croma_supersociedades_co`. Una búsqueda por CLI (país + CIIU + departamento) deja filas en `busquedas`, `leads`, `lead_fuentes`, `cumplimiento` y `costos`, deduplicadas por `(pais, id_fiscal)`. La migración `0002` crea las tablas con RLS y cierra `anon`/`authenticated`. Sin IA, sin endpoint HTTP, sin columnas sensibles.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI (sin cambios), SQLAlchemy 2 Core + psycopg 3, pydantic-settings. **Cambian:** `httpx` pasa de dev a runtime (lo usa el adaptador); se suma `pyyaml` (no está en `uv.lock`). Nada más.
**Storage**: Postgres (Supabase en prod; `postgres:16` en CI). Migración a mano `supabase/migrations/0002_descubrimiento.sql`.
**Testing**: pytest; `httpx.MockTransport` para Croma; import-linter (`layers` + el `forbidden` del 001).
**Target Platform**: CLI local (`uv run python -m app.cli buscar …`); la API no expone nada nuevo.
**Project Type**: web app (solo toca `backend/`).
**Performance Goals**: N/A.
**Constraints**: ≤ 4 h. Croma ~100 requests/24 h y 1.500 créditos/mes: los tests no tocan la red, una sola corrida real (tarea 8), avisada.
**Scale/Scope**: 1 módulo, 1 puerto, 1 adaptador, 7 tablas, 1 comando de CLI.

## Constitution Check

*GATE: antes de Phase 0 y re-chequeado tras Phase 1.*

| Principio | Qué entrega este slice | Estado |
|---|---|---|
| I Hexagonal | Contrato `layers` (`infraestructura > aplicacion > dominio`) para `app.modulos.descubrimiento`, con canario. Puerto como `Protocol` en `dominio/`. Catálogo `clave → clase` solo en `infraestructura/adaptadores/__init__.py`. Suite de contrato en `tests/contratos/`. Test de que todo adaptador está declarado. | ✅ |
| II Test primero | Cada tarea arranca en rojo (ver `tasks.md`). El advisor revisa RLS, privilegios, costos y dedup antes de aceptarlos. Marca "src sin tests" del 001: sigue diferida (ver Complexity). | ⚠️ |
| III Tenant/RLS | Todas las tablas con `tenant_id` + RLS `USING/WITH CHECK`; `tenants` por `id`. Unidad de trabajo con `set_config('app.tenant_id', …, true)` como primera sentencia. `test_rls[tabla]`, `test_privilegios_supabase.py` (con `supabase_simulado.sql`) y `test_tenant_no_sobrevive_al_commit`. `fuente_cache` sin tenant, justificada. | ✅ |
| IV Migraciones | `0002` a mano. `test_migrar_local_desde_vacio_dos_veces_sin_drift` pasa a comparar contra las versiones de `supabase/migrations/*.sql`. `app/modelos.py` declara las 7 tablas para que el drift check siga vacío. | ✅ |
| V Seguridad | `CROMA_API_KEY` por `Settings` (entorno), nunca en logs ni en el dominio. `sembrar_tenant.py` pide la URL de `postgres` por `getpass`, con test de que no la imprime. | ✅ |
| VI Contacto cifrado | N/A: NIT, razón social y dirección de una persona jurídica no son dato personal. `telefono`/`email` no entran en este slice. | — |
| VII Cumplimiento | `tipo_titular` NOT NULL (default `desconocido`); Supersociedades → `juridica`. Fila en `cumplimiento` por lead nuevo, en la misma transacción que el lead. | ✅ |
| VIII Costos | Una fila en `costos` por intento HTTP, escrita antes de que `buscar` retorne. `test_costos_por_adaptador` exige `RegistroCostos` en el constructor. Integración contra Postgres real. | ✅ |
| IX Evals | N/A (sin IA). | — |
| X Doc viva | `docs/arquitectura-backend.md`: módulo, puerto, registro, cómo agregar un adaptador (ver pregunta abierta 12). | ⚠️ |

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
    filtros: Mapping[str, str]        # claves del vocabulario de fuentes.yaml: ciiu, departamento, …

@dataclass(frozen=True)
class EmpresaCruda:
    pais: str
    nombre: str
    fuente: str                       # clave del registro, p. ej. "croma_supersociedades_co"
    url_origen: str
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

**Qué recibe:** `CriteriosICP` + `pagina` (este slice solo usa 1). **Qué devuelve:** `PaginaEmpresas` con `EmpresaCruda` ya normalizadas. **Qué lanza:**
- `CriterioNoSoportado`: alguna clave de `criterios.filtros` no está en `meta.filtros`. Se lanza antes de cualquier request.
- `LimiteFuenteAgotado`: el adaptador no llama porque el contador de 24 h llegó al límite.
- `FuenteNoDisponible`: los intentos (con su reintento) fallaron. Las filas de `costos` ya quedaron escritas.

Funciones de dominio: `normalizar_nit(texto) -> str` y `cubre(meta, criterios) -> bool` (`pais ∈ paises` o `"*" ∈ paises`, y `set(filtros) ⊆ meta.filtros`).

**Lo que los slices siguientes agregan sin tocar la firma:** campos opcionales en `EmpresaCruda` (`telefono`, `email` en la 003, cifrados al persistir por la 006); nuevas claves en el catálogo y en `fuentes.yaml` (003, 011). Un cambio a `buscar` o a los tipos de retorno es cambio de puerto y pide spec.

`RegistroCostos` y `RepositorioLeads` (también Protocols en `dominio/`):

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
    ts: datetime | None = None        # None = now() de la base (ver pregunta 7)

class RegistroCostos(Protocol):
    def registrar(self, op: OperacionCosto) -> None: ...
    def requests_24h(self, proveedor: str) -> int: ...
    def creditos_mes(self, proveedor: str) -> Decimal: ...

class RepositorioLeads(Protocol):
    def crear_busqueda(self, criterios: CriteriosICP) -> UUID: ...
    def obtener_o_crear_lead(self, e: EmpresaCruda) -> tuple[UUID, bool]: ...   # (id, nuevo)
    def crear_cumplimiento(self, lead_id: UUID, e: EmpresaCruda, licencia: str) -> None: ...
    def agregar_lead_fuente(self, lead_id: UUID, busqueda_id: UUID, e: EmpresaCruda, licencia: str) -> None: ...  # ON CONFLICT DO NOTHING
```

## Registro: `config/fuentes.yaml`

- `cargar_registro(ruta_yaml, catalogo) -> Registro` en `aplicacion/`. Lee **solo** `fuentes_descubrimiento`.
  - Entradas con `habilitado: false`: se ignoran y no se validan.
  - Entradas con `habilitado: true` sin `paises` o sin `filtros`: `RegistroInvalido`.
  - Habilitadas con clave en el catálogo: van a `Registro.fuentes` como `(clase, MetaFuente)`.
  - Habilitadas sin clave en el catálogo: van a `Registro.sin_implementacion` (hoy `{"croma_dian_trade_co", "osm_overpass"}`); no rompen.
  - Clave del catálogo ausente del YAML: `RegistroInvalido`.
- `catalogo = {"croma_supersociedades_co": CromaSupersociedades}` en `infraestructura/adaptadores/__init__.py`. Es el único lugar que nombra clases concretas.
- La raíz de composición es `app/cli.py`: construye cada adaptador con `meta`, `RegistroCostos`, transporte `httpx`, caché, tarifa resuelta, límites, API key y `lote_id`, y le pasa a `EjecutarBusqueda` instancias ya armadas.
- Conectar o desconectar una fuente: `habilitado: true/false` en el YAML. Sumar una fuente: clase + clave en el catálogo + entrada en el YAML + fábrica en la suite de contrato.

## Suite de contrato

`backend/tests/contratos/test_fuente_descubrimiento.py`, parametrizada sobre `catalogo` (no sobre una lista escrita a mano). Cada adaptador se construye con transporte falso y `RegistroCostos` falso por una fábrica en `backend/tests/contratos/fabricas.py` (`clave → fabrica(transporte, registro)`, con su respuesta sintética).

- `::test_hay_fabrica_para_cada_clave_del_catalogo`: sin esto, un adaptador nuevo sin fábrica dejaría la suite verde sin correr.
- `::test_devuelve_empresas_normalizadas[clave]`: cada empresa trae `pais`, `nombre`, `fuente == clave`, `url_origen`, `as_of` con zona, y `actividad.sistema`.
- `::test_registra_costo_antes_de_devolver[clave]`: una fila por intento HTTP en el falso cuando `buscar` retorna.
- `::test_rechaza_criterio_no_soportado[clave]`: una clave fuera de `meta.filtros` lanza `CriterioNoSoportado` y el transporte recibe 0 requests.

La 003 y la 011 entran a esta suite agregando su clave y su fábrica; no escriben tests de contrato propios.

## Dónde escribe en `costos` y en `cumplimiento`

| Qué | Quién | Cuándo | Transacción |
|---|---|---|---|
| `costos`: 1 fila por intento HTTP enviado, `tipo='croma_consulta'`, `proveedor='croma'`, `fuente=<clave>`, `lead_id=None`, `lote_id=<busqueda_id>` | el adaptador, vía `RegistroCostos.registrar` | después de cada respuesta o timeout, antes de devolver o de lanzar | propia y corta (pregunta 1) |
| `costos` en hit de caché | nadie | — | — |
| `cumplimiento`: 1 fila por lead **nuevo** (`fuente`, `licencia`, `url_origen`, `as_of`, `base_legal=NULL`) | `EjecutarBusqueda`, vía `RepositorioLeads.crear_cumplimiento` | al insertar el lead | la misma que el lead: no hay lead sin fila |
| `lead_fuentes`: 1 por `(lead, fuente, busqueda)` | `EjecutarBusqueda` | siempre, nuevo o existente | la del lead, `ON CONFLICT DO NOTHING` |

Valores de la fila de `costos`:
- 200: `unidades=1` (dataset), `costo_unitario = tarifas.croma.usd_por_credito`.
- 5xx o timeout: `unidades=0`, `costo_unitario=0`. Cuenta para el límite de 24 h.
- `gratis = creditos_mes("croma") < limites.croma_creditos_gratis_mes`, leído antes del intento.

## Límite de Croma y caché

Orden dentro de `buscar`:
1. Validar criterios (`CriterioNoSoportado`).
2. Caché: `hash_params = sha256(json.dumps(body, sort_keys=True))` sobre `(proveedor, endpoint, hash_params)`. Hay hit: devuelve desde `respuesta`, con su `as_of`, sin request y sin fila en `costos`.
3. Antes de **cada** intento: si `requests_24h("croma") >= limites.croma_requests_por_24h`, `LimiteFuenteAgotado` (pregunta 4).
4. Request con `per_page=100`, timeout 10 s. Ante 502, 503 o timeout, un reintento con backoff. Cada intento escribe su fila.
5. En 200: upsert en `fuente_cache` y mapeo a `EmpresaCruda`.

Contadores en `postgres_costos`, sobre `costos` filtrado por `proveedor`:
- `requests_24h`: `COUNT(*)` con `ts > now() - interval '24 hours'`.
- `creditos_mes`: `SUM(unidades)` con `ts >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'`.
- `# ponytail:` cuentan por tenant (RLS). Con un tenant coincide con la cuenta de Croma; con varios, contador global.

`fuente_cache` es global (sin `tenant_id`, sin RLS), UNIQUE `(proveedor, endpoint, hash_params)`, `GRANT SELECT, INSERT, UPDATE` a `app_rt`. Sin TTL en este slice (pregunta 6). No se expone por API: Croma no se redistribuye.

## Datos (migración `0002_descubrimiento.sql`)

Las tablas y restricciones son las de la spec (sección Decisiones técnicas), sin cambios. Lo que el plan agrega:
- `id uuid PRIMARY KEY DEFAULT gen_random_uuid()` en todas; `tenant_id uuid NOT NULL REFERENCES tenants(id)`.
- FKs: `lead_fuentes.lead_id`, `lead_fuentes.busqueda_id`, `cumplimiento.lead_id` → `leads`/`busquedas`. `costos.lead_id` y `costos.lote_id` sin FK: un costo no se pierde porque se borre un lead.
- `costos.ts timestamptz NOT NULL DEFAULT now()`, índice `(tenant_id, proveedor, ts)` para los contadores.
- `GRANT` a `app_rt`: `SELECT, INSERT, UPDATE, DELETE` en las tablas de tenant; `SELECT` en `tenants`; `SELECT, INSERT, UPDATE` en `fuente_cache`.
- Al final, el bloque `DO` de `REVOKE` a `anon`/`authenticated` (solo si existen en `pg_roles`).
- `backend/app/modelos.py` declara las 7 tablas en SQLAlchemy Core, para que `compare_metadata` siga vacío. Riesgo: la columna `GENERATED` de `idioma_contacto` va con `Computed(..., persisted=True)`; si Alembic igual reporta diferencia, se documenta y se ajusta el comparador, no la migración.

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
├── pyproject.toml                      # contrato layers; httpx a runtime; pyyaml
├── app/config.py                       # + croma_api_key: SecretStr | None
├── app/db.py                           # + unidad de trabajo con set_config(..., true)
├── app/modelos.py                      # 7 tablas en Core (drift)
├── app/cli.py                          # raíz de composición: `buscar`
├── app/modulos/descubrimiento/
│   ├── dominio/{modelos.py, puertos.py, nit.py, errores.py}
│   ├── aplicacion/{ejecutar_busqueda.py, registro.py}
│   └── infraestructura/
│       ├── adaptadores/{__init__.py, croma_supersociedades.py}
│       └── persistencia/{postgres_costos.py, repositorio_leads.py, repositorio_cache.py}
├── scripts/{supabase_simulado.sql, sembrar_tenant.py}
└── tests/
    ├── arquitectura/{test_import_linter.py, test_registro_adaptadores.py, test_costos_por_adaptador.py, test_migraciones.py}
    ├── contratos/{fabricas.py, test_fuente_descubrimiento.py}
    ├── fixtures/croma_supersociedades_sintetica.json
    ├── unit/descubrimiento/{test_registro.py, test_croma_supersociedades.py, test_ejecutar_busqueda.py}
    └── integration/{test_leads_repo.py, test_costos_repo.py, test_rls.py, test_privilegios_supabase.py, test_sembrar_tenant.py}
supabase/migrations/0002_descubrimiento.sql
.github/workflows/ci.yml                # supabase_simulado.sql entre roles.sql y migrar_local.sh
.claude/skills/slice-tdd/SKILL.md       # slice/ → feature/ (lo pide la spec)
docs/arquitectura-backend.md
```

**Structure Decision**: módulo hexagonal según el principio I. `aplicacion/` no importa `infraestructura/`; la CLI es la única que conoce las dos.

## Orden de tareas

El de la spec (pasos 1 a 9), detallado en [tasks.md](./tasks.md).

## Preguntas abiertas

Cada una con el default que se aplica si no hay respuesta antes de la tarea que la necesita.

1. **Transacción de `costos`.** Si la fila de costo va en la misma transacción que los leads, un fallo posterior hace rollback del costo: se pierde el gasto (VIII) y el contador de 24 h queda por debajo de lo real. *Default:* `postgres_costos.registrar` abre su propia transacción corta (con su `set_config` del tenant). Lo mismo para el upsert de `fuente_cache`.
2. **`lote_id` y cómo llega al adaptador.** La firma `buscar(criterios, pagina)` no lo trae. *Default:* `lote_id = busqueda_id`, pasado al constructor; la CLI arma los adaptadores por búsqueda.
3. **Quién lee `limites`.** La spec dice que `cargar_registro` lee solo `fuentes_descubrimiento`, pero el adaptador necesita `limites.croma_*`. *Default:* la CLI lee `limites` y se los pasa al constructor; `cargar_registro` no cambia.
4. **Límite entre intentos.** Con 99 requests previas, un 502 deja 100: ¿se hace el reintento (101)? *Default:* se chequea antes de cada intento; no se hace, y sale `LimiteFuenteAgotado`. Los tests de la spec (98 + 2 = 100) siguen valiendo.
5. **4xx (400, 401, 404, 422).** La spec no dice si cuentan créditos ni si se reintentan. *Default:* no se reintentan, fila con `unidades=0` y `costo_unitario=0`, y `FuenteNoDisponible`. Se verifica en la corrida real.
6. **TTL de `fuente_cache`.** Sin vencimiento, Supersociedades (anual) no cambia, pero un ICP repetido nunca refresca. *Default:* sin TTL en este slice; `as_of` del caché viaja en la `EmpresaCruda` para que se vea la edad.
7. **`ts` de `costos`: reloj de la app o de la base.** Los contadores usan `now()` de la base. *Default:* `ts` lo pone la base (`DEFAULT now()`); `OperacionCosto.ts` queda opcional.
8. **NIT sin guion con DV pegado** (`9001234567`). `normalizar_nit` no puede saber si el último dígito es DV. *Default:* solo se corta el DV si viene tras `-`; si no, quedan los dígitos. Se confirma con la forma real de Supersociedades en la tarea 8.
9. **Formato de `departamento`.** La CLI usa `11` (código DANE); no está verificado si Croma espera código o nombre. *Default:* código DANE, mapeado en el adaptador si hace falta; se confirma en la tarea 8.
10. **`url_origen` y `as_of` de Croma.** Ninguno de los dos está definido para una respuesta de API. *Default:* `url_origen` = proveedor + `endpoint` de `fuentes.yaml` (sin query ni key); `as_of` = momento de la respuesta, o el `as_of` del caché en un hit.
11. **Errores de una fuente en `EjecutarBusqueda`.** "Se reporta en la búsqueda; no se traga" no dice si la búsqueda sigue con las otras fuentes. *Default:* captura `LimiteFuenteAgotado` y `FuenteNoDisponible` por fuente, sigue con las demás y los devuelve en el resultado; `busquedas.estado` queda `con_errores`. Los valores de `estado` (`creada`, `terminada`, `con_errores`) tampoco están en la spec.
12. **`docs/arquitectura-backend.md` no existe.** El 001 (T033) dejó su creación a la 013; la constitución (X) y el paso 9 de la spec la piden en el mismo PR. *Default:* se crea acá con la sección del módulo, y la 013 la consolida.
13. **`RegistroCostos` vive en `descubrimiento/dominio`.** La 006, 007 y 008 lo van a necesitar desde otros módulos, y un módulo importando el dominio de otro no está regulado todavía. *Default:* queda donde dice la spec; se mueve a un módulo `costos` en el 005, que es su dueño.
14. **Vocabulario de filtros entre fuentes.** `croma_*` usa `ciiu`/`departamento` y `osm_overpass` usa `ciudad`/`tipo_negocio`: con `cubre()` estricto, un ICP de CIIU + departamento nunca elige OSM. *Default:* estricto en este slice; la traducción de criterios es de la 003.
15. **`PaginaEmpresas` vs lista.** La spec dice "devuelve `EmpresaCruda` normalizada"; la skill `fuentes-publicas` fija `PaginaEmpresas`. *Default:* `PaginaEmpresas(empresas, total)`, porque el 005 necesita `total` para la vista previa.

## Complexity Tracking

| Desvío | Por qué | Alternativa descartada |
|---|---|---|
| Marca "PR toca src sin tests" (II), sigue diferida | No entra en ≤ 4 h junto al primer módulo; lo cubre la revisión humana del PR | Meterla acá y recortar tests de RLS |
| `httpx` a runtime y `pyyaml` nuevo | El adaptador y el registro los necesitan en producción | `urllib` (sin `MockTransport`) o parsear YAML a mano |
| `fuente_cache` sin RLS | Datos públicos de gobierno, no del tenant; compartirla ahorra cupo de Croma | Caché por tenant: gasta el doble de un cupo de 100/día |
