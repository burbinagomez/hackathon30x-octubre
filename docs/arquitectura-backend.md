# Arquitectura del backend

(Cada slice suma su sección; la 013 consolida.)

## Intake, Puerta A ("ya me compran", spec 010)

`POST /intake/lookalike {nombres}` -> `{sugerencia, explicacion, resueltos, no_resueltos, costo_usd}`. No crea búsquedas ni leads.

- `app/modulos/intake/dominio/`: `normalizar_nombre` (sin tildes, sin sufijo societario), `agregar_distribucion` (puro: moda de CIIU y de
  departamento por NIT único, top 3 con conteo, `ingresos_min=None`, solo matrícula activa, cámara desconocida no suma),
  `Sugerencia` (forma del body de vista previa) y los puertos `BuscadorRazonSocial` / `CoincidenciaRues` (`Protocol`, cumplidos por estructura).
- `intake/aplicacion/resolver_lookalike.py`: 5 a 50 nombres, dedup antes de consultar, un `ContextoCosto(fuente='intake', lote_id)` para toda la
  corrida, 0 o 2+ NIT distintos = no resuelto. No escribe costos.
- `descubrimiento/.../datos_gov_co_rues.py::buscar_coincidencias`: busca por razón social en `c82u-588k` (SoQL con el texto escapado, lista
  blanca de columnas), una fila de cómputo por request (`fuente='intake'`, `lead_id=NULL`, `lote_id` del contexto) escrita antes de devolver.
  `buscar()` no cambia.
- `app/api/intake_lookalike.py`: la raíz de composición que une las dos puntas (intake no importa descubrimiento: contrato `forbidden`).
  Departamento = cámara -> `camaras_co.yaml` (si la cámara cubre varios, el de menor código). Los nombres pegados no se persisten ni se loguean.
- Respeta `datos_gov_co_rues.habilitado` de `fuentes.yaml`: desconectada, responde 503 `lookalike_no_disponible`.

## Contacto por email (spec 007)

Envío del `mensaje_base` de una búsqueda a leads jurídicos con canal publicado, baja por enlace y tasa de respuesta. Solo CLI y una ruta pública.

- `app/modulos/contacto/dominio/`: `plantilla` (compone y valida remitente, canal de origen, enlace de baja y privacidad), `tokens` (HMAC con
  propósito: un token `msgid` no sirve como `baja`) y los puertos (`Protocol`):
  - `CanalContacto.enviar(MensajeSaliente)`: registra el costo antes de devolver o lanzar; transporte caído = `CanalNoDisponible` sin la dirección.
  - `LeadsContactables.de_busqueda(busqueda_id, canal)`: jurídicas, contactables, sin opt-out. Sin adaptador hasta que mergee la 006:
    `cli._armar_envio_postgres` corta con `NotImplementedError`.
  - `RepositorioContactos`: la elegibilidad legal (jurídica + fila de `cumplimiento` + sin opt-out) vive en SQL y se reevalúa al crear, al
    `reclamar` (que fija `base_legal`) y en `vigente`, justo antes de mandar. `dar_de_baja` y `marcar_respondio` son monotónicos.
- `contacto/aplicacion/envio.py::EnviarABusqueda`: dos pasos. `vista_previa` (`enviar --dry-run`) deja contactos `aprobado`; `enviar` solo manda
  esos, tope 20 por corrida, y aborta con `MensajeCambio` si el `mensaje_base` cambió. `EMAIL_MODO=prueba` (default) solo manda a
  `EMAIL_PRUEBA_DESTINOS`; con `real`, la CLI exige que `/baja/{token}` exista en la api.
- `contacto/aplicacion/baja.py::DarDeBaja`: el token dice tenant y contacto; inválido = 404 genérico. La baja cierra todos los canales del lead.
- `contacto/infraestructura/`: `smtp_email` (SMTP genérico por Settings, Resend previsto; credenciales y direcciones nunca en logs, repr ni
  excepciones) y `repositorio_contactos` (Postgres, RLS por `unidad_de_trabajo`). Contrato `forbidden`: el dominio no importa `smtplib` ni
  `cryptography`.
- CLI: `enviar [--dry-run] [--rehacer]`, `baja` (via humano), `respondio`, `tasa-respuesta` (vista `v_tasa_respuesta_canal`).
- `RUTAS_PUBLICAS` (`app/api/__init__.py`) = `/health` y `/baja/{token}`: el enlace llega por mail, sin sesión. GET confirma, POST da de baja
  (también one-click RFC 8058). Sin `BAJA_SECRET`, 404. Toda ruta nueva fuera de esa lista exige sesión, y un test lo fija.
- Migración `0009_contactos.sql`: tabla `contactos` (sin DELETE para `app_rt`), vistas `v_leads_con_opt_out` y `v_tasa_respuesta_canal`
  (SELECT a `app_rt`, nada a `anon`/`authenticated`).

## Lista de leads: contacto como booleano (005, enmienda)
`GET /leads` y `GET /busquedas/{id}/leads` devuelven `tiene_telefono`/`tiene_email` calculados en SQL con `IS NOT NULL` sobre las columnas cifradas (nunca se leen ni descifran), solo para jurídicas; natural o desconocido van `null`. El filtro `con_contacto=true` (jurídica con teléfono o correo) se agrega con `AND` al filtro de alcance en `RepositorioLeadsPostgres._pagina`.

## Tablero: embudo por fuente (spec 005)

`GET /tablero/fuentes` suma por fuente y en `total` cuatro conteos de leads únicos: `enriquecidos` (`enriquecido_en` no nulo), `contactables`,
`con_telefono` (jurídicas con `telefono_cifrado` no nulo) y `calificados` (`calificaciones.calificado`). SQL inline en
`tablero/.../repositorio_tablero.py`, sin DDL, bajo la RLS de la sesión. Un lead de dos fuentes cuenta en las dos; el total no duplica.
`sin_atribuir` (costo sin lead) devuelve `null` en los cuatro; una fuente con leads y sin enriquecimiento devuelve 0 real. Solo `count`: el
repositorio nunca selecciona nombre, dirección ni contacto (lo vigila `test_cifrado.py`).
