# Data model — 001 Walking skeleton

Sin entidades de negocio (fuera del alcance). Solo esto:

| Objeto | Qué es | Reglas |
|---|---|---|
| `alembic_version` | tabla de Alembic | `0001_inicial` es `head` y está vacía |
| `app/modelos.py` | `metadata = MetaData()` vacío | sin importar `config`; es el `target_metadata` de Alembic |
| `postgres` (owner de Railway) | SUPERUSER | solo corre `roles.sql` a mano; nunca en CI ni en runtime |
| `app_mig` | migraciones | `LOGIN NOSUPERUSER NOBYPASSRLS`, dueño del schema `public`; su URL vive solo en el Environment `produccion` (job `migrar`) |
| `app_rt` | runtime de `api` | `LOGIN NOSUPERUSER NOBYPASSRLS`, no es dueño de nada ni puede hacer `CREATE` en `public`; DML vía `DEFAULT PRIVILEGES FOR ROLE app_mig` (tablas + secuencias) |
