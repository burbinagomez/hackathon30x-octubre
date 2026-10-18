-- 0005: convalida los CHECK de titular. Sin condición: si en prod queda un lead de prueba en claro, falla y la
-- migración no se registra (el deploy cae); el dueño los borra a mano y se reintenta. No hay backfill.
ALTER TABLE public.leads VALIDATE CONSTRAINT leads_nombre_segun_titular_ck;
ALTER TABLE public.leads VALIDATE CONSTRAINT leads_direccion_segun_titular_ck;
-- Sobre una base ya convalidada es un no-op, así que desde vacío corre sin efecto y migrar_local.sh dos veces no cambia nada.
