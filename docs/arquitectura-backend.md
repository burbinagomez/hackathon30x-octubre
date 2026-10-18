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

## Tablero: embudo por fuente (spec 005)

`GET /tablero/fuentes` suma por fuente y en `total` cuatro conteos de leads únicos: `enriquecidos` (`enriquecido_en` no nulo), `contactables`,
`con_telefono` (jurídicas con `telefono_cifrado` no nulo) y `calificados` (`calificaciones.calificado`). SQL inline en
`tablero/.../repositorio_tablero.py`, sin DDL, bajo la RLS de la sesión. Un lead de dos fuentes cuenta en las dos; el total no duplica.
`sin_atribuir` (costo sin lead) devuelve `null` en los cuatro; una fuente con leads y sin enriquecimiento devuelve 0 real. Solo `count`: el
repositorio nunca selecciona nombre, dirección ni contacto (lo vigila `test_cifrado.py`).
