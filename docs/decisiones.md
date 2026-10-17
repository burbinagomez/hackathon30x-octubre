# Decisiones (registro)

| Fecha | Decisión | Razón | Fuente |
|---|---|---|---|
| 2026-10-16 | Solo se contacta a personas jurídicas por canales publicados | SIC 17-96489: datos del registro son públicos pero su uso para ofrecer productos requiere autorización del titular (persona natural) | docs/prd.md §2 |
| 2026-10-16 | Email es el primer toque; WhatsApp solo validado y acotado | Meta API exige opt-in; cold outreach no permitido oficialmente | docs/prd.md §2 |
| 2026-10-16 | Croma es enriquecimiento, no descubrimiento, y no cuenta como fuente gratuita obligatoria | Busca por NIT/nombre; tier gratis de API de pago | docs/prd.md §2 |
| 2026-10-17 | Nada de otros proyectos del equipo entra al repo (cuentas, código, credenciales) | Regla del dueño; repo público | constitution.md |
| 2026-10-17 | Arquitectura hexagonal con registro de adaptadores (`config/fuentes.yaml`): toda fuente de entrada y salida se conecta/desconecta por config y pasa una suite de contrato por puerto | Requisito del dueño; permite cambiar de fuente por país sin tocar dominio | constitution.md §I |
| 2026-10-17 | Croma pasa a ENCONTRAR como origen de datos principal (multi-país) vía Supersociedades CO, DIAN Trade CO y SIEM MX; RUES/SUNAT quedan como verificación | Verificado: esos endpoints aceptan filtros (CIIU, dpto, ingresos, SCIAN); RUES solo por nombre/NIT. Límite ~100 req/24h y 1.500 créditos gratis | docs/prd.md §2–3, skill fuentes-publicas |
| 2026-10-17 | datos.gov.co queda como adaptador construido pero `habilitado: false` | Respaldo a un flag si el jurado objeta Croma como "gratuita" o si se agota el tier; demuestra el conectar/desconectar | config/fuentes.yaml |
| 2026-10-17 | OSM se mantiene como segunda fuente de descubrimiento (la gratuita de verdad) y única para PE/BR | Croma no tiene registro de empresas para BR ni descubrimiento para PE; Supersociedades sesga a empresas que reportan | skill fuentes-publicas |
| 2026-10-17 | El esquema pasa de Alembic a `supabase/migrations/NNNN_nombre.sql` escritos a mano; prod migra con `supabase db push` en el job `migrar` (Environment `produccion`), CI y local con `scripts/migrar_local.sh` como superusuario. `app_mig` desaparece: `db push` corre como `postgres` y cada migración trae sus `GRANT` a `app_rt`. Alembic queda solo como librería del drift check | Decisión del equipo: una sola herramienta de esquema, la del proveedor de la base; el dominio no cambia | constitution.md §IV, specs/001-walking-skeleton/research.md R-migraciones |
