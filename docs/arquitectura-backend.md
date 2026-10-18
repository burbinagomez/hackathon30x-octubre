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

## Enriquecimiento: verificación de titular por nombre + ciudad (spec 006, enmienda 2026-10-18)

Un lead `desconocido` (todo OSM) pasa a `juridica` solo si su nombre normalizado coincide EXACTO con una sola empresa (un NIT) del RUES de
datos.gov.co (`c82u-588k`, activa) en la misma ciudad. Decisión del dueño: "Sí, nombre + ciudad". Todo lo demás falla cerrado a `desconocido`.

- Puerto `VerificadorTitular` (`enriquecimiento/dominio/puertos.py`): `verificar(lead_id, nombre, ciudad) -> VerificacionTitular(tipo_titular,
  motivo, constancia)`. Motivos: `match_unico`, `sin_match`, `ambiguo`, `sin_ciudad`, `pais_no_soportado`, `fuente_no_disponible`. Recibe el país del lead: fuera de CO no consulta ni cobra.
- `dominio/normalizar_titular.py`: mayúsculas, sin tildes ni puntuación, espacios colapsados; sufijos societarios finales (SAS, SA, LTDA, LTD, EU,
  SCA, SCS) se ignoran en el nombre (OSM no los trae, el RUES sí; la unicidad por NIT evita confundir "X LTDA" con "X SAS"); `D.C.` final se ignora en la ciudad.
- Adaptador `RuesDatosGov` (`infraestructura/adaptadores/rues_datos_gov.py`): reusa `DatosGovCoRues.buscar_coincidencias` de la 011 (mismo cliente que
  la Puerta A), detrás de un puerto propio (`BuscadorRazonSocialRues`); solo la raíz de composición los une. El RUES no trae municipio: la ciudad es el
  `municipio_sede` de la cámara (`config/camaras_co.yaml`). Una respuesta que llega al tope de 100 filas crudas (`truncada`) es `ambiguo`. Antes de subir, un segundo request de solo `count(*)` cuenta personas naturales homónimas en la cámara de la ciudad (el servidor las excluye); si hay alguna, `ambiguo`. Se revisa además que la matrícula sea `ACTIVA` y no natural.
- Se elige por config: `enriquecedores.rues_datos_gov_co.habilitado` en `fuentes.yaml` (`composicion.verificador_titular`); apagado, vuelve el stub
  `CromaRues` (siempre `desconocido`). Un request, 8 s de plazo: si la fuente falla, el lead queda `desconocido` y la corrida sigue.
- Costos: cada request escribe `socrata_descarga` (`proveedor='datos.gov.co'`, `lead_id` del lead, `fuente=NULL` como el resto del enriquecimiento)
  antes de devolver, también en fallas. El cliente calla el log de `httpx` mientras pide, porque la URL lleva el nombre del lead.
- `cumplimiento.solicitudes` recibe una entrada por cada lead verificado (`paso_a_claro` o `verificacion_titular`): `motivo`, `fuente`, `dataset`, `ts` y,
  con match, `nit`, `razon_social`, `municipio_sede_camara`, `codigo_camara`, `organizacion_juridica` y `estado_matricula`; con `ambiguo`, `candidatos` o `naturales_homonimas`. Nunca contacto ni el nombre del lead. Sin migración.
- Tests: `tests/unit/enriquecimiento/test_normalizar_titular.py`, `test_rues_datos_gov.py`, `tests/unit/test_composicion_verificador.py`,
  `tests/contratos/test_verificador_titular.py`, `tests/integration/test_verificacion_titular_rues.py`.

### Buscador de sitio web (006, enmienda 2026-10-18)
- Puerto `BuscadorSitioWeb` (`enriquecimiento/dominio/puertos.py`): `buscar(lead_id, razon_social, nit) -> EvidenciaSitioWeb | None`. Adaptador
  `DominioPorRazonSocial`. Dominio puro en `enriquecimiento/dominio/dominios.py`: `candidatos_de_dominio` (hasta 6: pegado y con guion x `.com.co`/`.com`/`.co`,
  sin sufijos societarios ni `EN LIQUIDACION`, sin palabras genéricas solas) y `verifica_pagina` (NIT con o sin puntos, o razón social completa).
- Flujo: DNS de cada candidato (no resuelve = sin HTTP) -> SSRF (`validar_destino` de `sitio_web`, por salto, conexión a la IP validada) -> GET de la portada
  (4 s, mismo User-Agent, redirecciones solo dentro del dominio) -> verificación. Nunca se acepta un dominio sin verificar; el primero verificado gana.
- `EnriquecerLead`: jurídica sin web -> buscador; si halla, `leads.web` (columna existente, sin DDL; nunca pisa la que ya traía el lead) y sigue `sitio_web`.
  Evidencia en `cumplimiento.solicitudes` (`tipo=sitio_web_encontrado`, `fuente`, `url`, `motivo`, `ts`), nunca contacto. Costos: `web_fetch` por request, con `lead_id`.
- Tanda de la API: `EnriquecerLead(max_hilos=8).ejecutar(busqueda, TANDA, presupuesto_s=60)`. Los leads corren en paralelo; el repo lo escribe solo el hilo
  principal; lo que no terminó en 60 s queda pendiente ("Seguir con los que quedan"). Plazo de 12 s por lead para el buscador.
- Config: `enriquecedores.dominio_por_razon_social.habilitado` (`composicion.buscador_sitio_web`); en `false` un lead sin web se queda sin web.
- Tests: `tests/unit/enriquecimiento/test_dominios.py`, `test_dominio_por_razon_social.py`, `test_enriquecer_lead_sitio.py`,
  `tests/unit/test_composicion_buscador.py`, `tests/integration/test_buscar_sitio_web.py`.

## Libro de costos: pantalla de solo lectura (spec 005)

`GET /costos?pagina=N[&busqueda_id=]` (`api/costos.py`, `costos/infraestructura/repositorio_libro.py`): SQL inline sobre `costos`, sin DDL, bajo
la RLS de la sesión. 50 por página, `ts` descendente. Trae `total_usd` (valor de lista), `total_real_usd` (sin lo gratis) y subtotales
`por_tipo` y `por_fuente` de TODO el libro (o de la búsqueda filtrada), no de la página. `busqueda_id` = `lote_id` (el lote es la búsqueda); el
filtro deja fuera los costos por lead sin lote. `lead` sale como booleano: el `lead_id` no sale nunca.

## Tablero: embudo por fuente (spec 005)

`GET /tablero/fuentes` suma por fuente y en `total` cuatro conteos de leads únicos: `enriquecidos` (`enriquecido_en` no nulo), `contactables`,
`con_telefono` (jurídicas con `telefono_cifrado` no nulo) y `calificados` (`calificaciones.calificado`). SQL inline en
`tablero/.../repositorio_tablero.py`, sin DDL, bajo la RLS de la sesión. Un lead de dos fuentes cuenta en las dos; el total no duplica.
`sin_atribuir` (costo sin lead) devuelve `null` en los cuatro; una fuente con leads y sin enriquecimiento devuelve 0 real. Solo `count`: el
repositorio nunca selecciona nombre, dirección ni contacto (lo vigila `test_cifrado.py`).
