# Arquitectura del frontend

(Cada slice suma su sección; la 013 consolida.)

## Intake, Puerta A (spec 010)

`src/busqueda/IntakeLookalike.tsx`: textarea (una empresa por línea, 5 a 50), "Usar ejemplo" (`ejemploLookalike.ts`, sintético), explicación con
conteos y no resueltos. Entrega la sugerencia con la prop `alSugerir(sugerencia)`; quien lo monta (las pestañas de `NuevaBusqueda`) prellena
el formulario y salta a "Filtros". Los nombres viven solo en el estado del componente. Textos en `intake.lookalike.*` (es y en).

## ListaLeads: filtro "Solo con contacto"
`ListaLeads` guarda el estado del checkbox y llama `cargar(pagina, conContacto)`; al cambiarlo vuelve a la página 1. `api.ts` agrega `con_contacto=true` solo cuando está marcado. Teléfono y Correo se pintan "Sí" o "—"; `null` (natural) queda vacío.

## Libro de costos (`costos/`)

Ruta `/costos` (opcional `?busqueda_id=`, solo si es uuid). `Costos.tsx`: total y subtotales por tipo y por fuente arriba, tabla de operaciones
en `.tabla-scroll` (scroll horizontal dentro del contenedor, sirve a 360 px) y paginación de a 50. Enlaces: "Ver costos" en el Tablero y en cada fila
de `/busquedas`. Textos en `costos.*` (es/en).

## Tablero: embudo por fuente

`Tablero.tsx` pinta, bajo la tabla, una sección `region` "Embudo por fuente" con un grupo por fuente (y el total): encontrados, únicos,
enriquecidos, contactables, con teléfono, calificados. Cada paso es texto (etiqueta, número, % de únicos) más una barra decorativa
(`aria-hidden`, ancho proporcional a únicos, tope 100 %) con `--color-acento` sobre la pista `--color-pista` (gris), claro y oscuro. Si la API no
manda ningún campo del embudo (backend viejo) la sección no se pinta; un valor `null` se muestra "—", nunca 0. Textos en `tablero.embudo*`.
