# Arquitectura del frontend

(Cada slice suma su sección; la 013 consolida.)

## Intake, Puerta A (spec 010)

`src/busqueda/IntakeLookalike.tsx`: textarea (una empresa por línea, 5 a 50), "Usar ejemplo" (`ejemploLookalike.ts`, sintético), explicación con
conteos y no resueltos. Entrega la sugerencia con la prop `alSugerir(sugerencia)`; quien lo monta (las pestañas de `NuevaBusqueda`) prellena
el formulario y salta a "Filtros". Los nombres viven solo en el estado del componente. Textos en `intake.lookalike.*` (es y en).
