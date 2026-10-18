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

## Tablero: embudo por fuente (spec 005)

`GET /tablero/fuentes` suma por fuente y en `total` cuatro conteos de leads únicos: `enriquecidos` (`enriquecido_en` no nulo), `contactables`,
`con_telefono` (jurídicas con `telefono_cifrado` no nulo) y `calificados` (`calificaciones.calificado`). SQL inline en
`tablero/.../repositorio_tablero.py`, sin DDL, bajo la RLS de la sesión. Un lead de dos fuentes cuenta en las dos; el total no duplica.
`sin_atribuir` (costo sin lead) devuelve `null` en los cuatro; una fuente con leads y sin enriquecimiento devuelve 0 real. Solo `count`: el
repositorio nunca selecciona nombre, dirección ni contacto (lo vigila `test_cifrado.py`).
