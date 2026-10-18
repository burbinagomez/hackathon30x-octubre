# Implementation Plan: 007 — Email por SMTP, respuestas mínimas y baja

**Branch**: `feature/007-email` | **Date**: 2026-10-18 | **Spec**: `specs/007-email-respuestas/spec.md`

> Corte de demo (~6 h) de la spec. Referencias: `docs/prd.md` §9 punto 7, skills `libro-costos` y
> `cumplimiento-datos`, constitución. La 006 (contactable, `email_cifrado`) se construye en
> paralelo: este plan no importa nada de `app/modulos/enriquecimiento`.

## Summary

Un módulo nuevo, `app/modulos/contacto`, manda **un** email por lead contactable de una búsqueda,
con el `mensaje_base` de esa búsqueda y un pie fijo (identificación, origen del dato, cómo darse
de baja, `/privacidad`). El adaptador `smtp_email` vive detrás de `CanalContacto`, usa SMTP
genérico (Resend en la demo) y registra cada envío en `costos` antes de devolver, aunque falle.
Antes de mandar se setea `cumplimiento.base_legal`; sin base legal no sale nada. Las respuestas se
marcan a mano (`app.cli respondio`) y `app.cli tasa-respuesta` da la tasa por canal. BAJA, por
enlace público o marcada a mano, setea `cumplimiento.opt_out_at` y cierra todos los canales.

## Technical Context

- **Language/Version:** Python 3.12.
- **Primary Dependencies:** `smtplib`, `email.message`, `hmac` y `hashlib` de la stdlib. FastAPI y SQLAlchemy Core de la 002. **Ninguna dependencia nueva**: el servidor SMTP falso de los tests es un `socketserver` de ~50 líneas en `tests/smtp_falso.py`.
- **Storage:** Postgres, una migración a mano, la `0010` (abajo, pendiente de aprobación).
- **Testing:** pytest. Unit con falsos en memoria y contrato del adaptador contra el SMTP falso por socket. Integración contra Postgres real como `app_rt`. **Cero envíos reales en tests.**
- **Constraints:** ~6 h, un solo envío real avisado al final (a una casilla nuestra), cupo diario por `limites.email_max_por_dia` en `fuentes.yaml`.
- **Scale/Scope:** 1 módulo, 1 tabla, 2 vistas, 2 rutas públicas, 4 comandos de CLI.

## Constitution Check

| Principio | Qué entrega | Estado |
|---|---|---|
| I Hexagonal | `CanalContacto` y `LeadsContactables` son Protocols en `contacto/aplicacion/puertos.py`. `app.modulos.contacto` entra al `containers` de import-linter, y un contrato prohíbe `smtplib` y `cryptography` en `contacto.dominio`. | ✅ |
| II Test primero | Cada test con su mutación con nombre (ver `tasks.md`). Esqueletos antes del rojo: nunca `ImportError`. | ✅ |
| III Tenant/RLS | `contactos` con RLS `tenant_aislado`; vistas `security_invoker`. `test_rls[contactos]` y `test_privilegios_supabase` la toman solos. El tenant de `/baja/{token}` sale del token verificado. | ✅ |
| IV Migraciones | `0010` a mano, `app/modelos.py` suma `contactos`, drift vacío. | ⏸ DDL pendiente |
| V Seguridad | `SMTP_HOST/PORT/USUARIO/CLAVE`, `REMITENTE`, `BAJA_SECRET`, `API_BASE_URL` por `Settings`; clave y secreto como `SecretStr`. `smtp_seguridad='ninguna'` solo con host `localhost`/`127.0.0.1`. Ni la dirección ni la clave van a logs (`test_contacto_no_aparece_en_logs`, con `SMTPRecipientsRefused`). | ✅ |
| VI Contacto | La dirección sale descifrada solo dentro del adaptador de `LeadsContactables` y viaja en un campo `repr=False`. `contactos` no guarda la dirección. | ✅ |
| VII Cumplimiento | Solo `tipo_titular='juridica'` con canal publicado y sin `opt_out_at`. `base_legal='persona_juridica_canal_publicado'` en la misma transacción del reclamo; sin ella, `SinBaseLegal` y `descartado`. | ✅ |
| VIII Costos | Una fila `email_envio` por intento (`unidades=1`, `canal='email'`, `lead_id`, `lote_id=busqueda_id`, `gratis=true` con tarifa 0). `test_costos_por_adaptador` se extiende a los `CanalContacto`. | ✅ |
| IX Evals | N/A: el corte no tiene redactor LLM. | — |
| X Doc viva | `docs/arquitectura-backend.md` suma el módulo y `RUTAS_PUBLICAS`. | ✅ |

## Lo que se usa sin redefinir

- `RegistroCostos.registrar(OperacionCosto)` y `tarifas.yaml` (`email.usd_por_mensaje: 0.0`). El CHECK de `costos.tipo` ya trae `email_envio`.
- `cumplimiento` (0002): fila por lead creada en `repositorio_leads.py:23`; columnas `base_legal`, `opt_out_at`, `solicitudes`.
- `busquedas.mensaje_base` (0002).
- `Cifrador` (`app/seguridad/cifrado.py`) para descifrar `email_cifrado` en el adaptador Postgres, y su HKDF para derivar la clave de los tokens con `info` propio.
- `canales_contacto.smtp_email` ya está en `fuentes.yaml` con `habilitado: true`.

## Cambios de puerto

```python
class CanalContacto(Protocol):
    canal: str  # 'email'
    def enviar(self, mensaje: MensajeSaliente) -> ResultadoEnvio: ...
    # Registra el costo antes de devolver o de lanzar. Error de transporte → CanalNoDisponible
    # sin la dirección en el mensaje.

class LeadsContactables(Protocol):
    def de_busqueda(self, busqueda_id: UUID, canal: str) -> list[LeadContactable]: ...
    # Solo jurídicas, contactable, con canal publicado y sin opt-out (v_leads_con_opt_out).

@dataclass(frozen=True)
class LeadContactable:
    lead_id: UUID
    canal_origen: str                       # 'sitio_web' | 'osm_contacto' (pie del mensaje)
    direccion: str = field(repr=False)      # nunca en repr, logs ni excepciones
```

`LeadsContactablesFalso` en `tests/falsos.py` hasta que mergee la 006; después,
`LeadsContactablesPostgres` lee `leads.email_cifrado`, `email_canal`, `contactable` y
`tipo_titular`. Es el único archivo que cambia cuando llega la 0008.

## Diseño por área

- **Dominio (`contacto/dominio/`)**: `plantilla.componer(mensaje_base, remitente, canal_origen, url_baja)` y `plantilla.validar(...)` (pie completo, URL de baja exacta, < 100 palabras). `tokens.firmar(proposito, tenant_id, contacto_id)` / `verificar(...)`: HMAC-SHA256 truncado, `hmac.compare_digest`, propósito `baja` ≠ `msgid`. Errores: `SinBaseLegal`, `CanalNoDisponible`.
- **Aplicación**: `EnviarABusqueda(busqueda_id)` por lead: crear o tomar el `contacto` (`UNIQUE` por lead y canal), reclamar `aprobado→enviando` y setear `base_legal` en una transacción, chequear cupo, enviar fuera de la transacción, cerrar en `enviado` o volver a `aprobado`. `DarDeBaja(lead_id, via)`. `MarcarRespondio(contacto_id)`. `TasaRespuesta()`.
- **Aprobación humana**: el `mensaje_base` lo escribe una persona en la búsqueda, y `app.cli enviar --busqueda <id>` lo corre una persona que ve antes la vista previa (`--dry-run` imprime asunto, cuerpo y cantidad, sin direcciones). Ver P1.
- **Infraestructura**: `smtp_email.py` (`SMTP_SSL` en 465, `STARTTLS` en 587, texto plano, headers `List-Unsubscribe` + `List-Unsubscribe-Post` + `Message-ID` con el token). `repositorio_contactos.py`. `api/baja.py`: `GET /baja/{token}` confirma, `POST` da de baja (idempotente, one-click RFC 8058), token inválido → `404` genérico.
- **API**: `RUTAS_PUBLICAS = {"/health", "/baja/{token}"}` en `app/api/`, y `test_sin_token_da_401` pasa a excluir esa lista; `test_rutas_publicas_son_exactamente_estas` la fija.

## Migración

### DDL de la 0010 — PENDIENTE DE APROBACIÓN DE DANIEL

No hay archivo en `supabase/migrations` hasta que lo apruebes.

```sql
create table public.contactos (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenants(id),
  lead_id      uuid not null,
  busqueda_id  uuid not null,
  canal        text not null check (canal = 'email'),
  asunto       text not null,
  cuerpo       text not null,
  estado       text not null default 'aprobado' check (estado in
               ('pendiente_aprobacion','aprobado','enviando','enviado',
                'rebotado','no_entregable','descartado')),
  enviado_en   timestamptz,
  respondio_en timestamptz,
  bloqueo      boolean not null default false,
  creado_en    timestamptz not null default now(),
  unique (tenant_id, lead_id, canal),
  foreign key (tenant_id, lead_id) references public.leads (tenant_id, id),
  foreign key (tenant_id, busqueda_id) references public.busquedas (tenant_id, id),
  check ((estado in ('enviado','rebotado')) = (enviado_en is not null)),
  check (respondio_en is null or enviado_en is not null)
);
alter table public.contactos enable row level security;   -- sin FORCE, como la 0002
create policy tenant_aislado on public.contactos
  using (tenant_id = current_setting('app.tenant_id')::uuid)
  with check (tenant_id = current_setting('app.tenant_id')::uuid);
grant select, insert, update on public.contactos to app_rt;   -- sin delete
-- + el mismo bloque de la 0002 que revoca a anon/authenticated si existen.

create view public.v_leads_con_opt_out with (security_invoker = true) as
  select tenant_id, lead_id, opt_out_at from public.cumplimiento where opt_out_at is not null;

create view public.v_tasa_respuesta_canal with (security_invoker = true) as
  select canal,
         count(*) filter (where enviado_en is not null)   as contactados,
         count(*) filter (where respondio_en is not null) as respondieron,
         round(count(*) filter (where respondio_en is not null)::numeric
               / nullif(count(*) filter (where enviado_en is not null), 0), 4) as tasa
  from public.contactos group by canal;
grant select on v_leads_con_opt_out, v_tasa_respuesta_canal to app_rt;
```

- `message_id` no se guarda: sale del token firmado con `contacto_id`, así no hay columna que filtre.
- Las FKs compuestas usan los `unique (tenant_id, id)` que ya tienen `leads` y `busquedas` (0002:20 y :41).
- `v_leads_con_opt_out` es la versión simple: sin recorrer `fusionado_en` ni comparar `email_hmac`. Ver "Fuera del corte".
- `tasa` es `NULL` con 0 contactados: "sin dato", nunca división por cero.

## Validación (quickstart)

```bash
scripts/test-backend.sh tests/unit/contacto tests/contratos/test_smtp_email.py
scripts/test-backend.sh tests/integration/test_envio_email.py tests/integration/test_api_baja.py
uv run python -m app.cli enviar --tenant <id> --busqueda <id> --dry-run
uv run python -m app.cli enviar --tenant <id> --busqueda <id>
uv run python -m app.cli respondio --tenant <id> --contacto <id>
uv run python -m app.cli tasa-respuesta --tenant <id>
```

## Project Structure

```text
backend/app/modulos/contacto/
  dominio/{plantilla.py, tokens.py, errores.py}
  aplicacion/{puertos.py, enviar.py, baja.py, respuestas.py}
  infraestructura/{smtp_email.py, repositorio_contactos.py, leads_contactables_postgres.py}
backend/app/api/{baja.py, rutas_publicas.py}
backend/tests/{smtp_falso.py, falsos.py}
backend/tests/unit/contacto/  backend/tests/contratos/test_smtp_email.py
backend/tests/integration/{test_envio_email.py, test_api_baja.py, test_respuestas_manual.py}
```

## Fuera del corte

Redactor LLM y `jev_check`, IMAP y webhook, DSN y rebotes automáticos, DNS MX (solo sintaxis),
front de Mensajes y Respuestas, evals, `email_hmac` y opt-out recursivo por fusión, página
`/privacidad` del front (el pie apunta a la URL; la página es de quien tenga el front).

## Preguntas abiertas

| # | Pregunta | Propuesta |
|---|---|---|
| P1 | ¿Alcanza como aprobación humana que una persona escriba el `mensaje_base` y corra `enviar` después de ver el `--dry-run`? La spec pide aprobar cada borrador. | Sí para la demo: sin redactor LLM, todos los mensajes de una búsqueda son el mismo texto. Por eso `contactos` nace en `aprobado`. |
| P2 | Remitente y dominio de Resend. | `REMITENTE` por Settings; el dominio verificado en Resend es tuyo (panel externo). |
| P3 | Cupo diario. | `limites.email_max_por_dia: 20` en `fuentes.yaml`. |
| P4 | El envío real de la demo. | Uno solo, a una casilla nuestra, avisado antes. |

## Complexity Tracking

| Decisión | Por qué | Lo simple que se descartó |
|---|---|---|
| SMTP falso por socket en vez de un mock de `smtplib` | El contrato prueba headers reales, `SMTPRecipientsRefused` real y que la clave no aparece en logs. | Mockear `smtplib.SMTP`: no prueba el protocolo. |
| Reclamo `aprobado→enviando` | Dos corridas en paralelo no mandan dos emails. | Confiar en el `UNIQUE`: protege la fila, no el SMTP. |
