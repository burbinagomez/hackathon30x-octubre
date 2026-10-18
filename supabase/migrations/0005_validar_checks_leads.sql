-- NNNN: convalida los CHECK de titular. Corre en prod DESPUÉS de cifrar los leads viejos con T056.
-- Sin condición: si queda una fila no jurídica en claro, falla y la migración no se registra (se corrige y se reintenta).
ALTER TABLE public.leads VALIDATE CONSTRAINT leads_nombre_segun_titular_ck;
ALTER TABLE public.leads VALIDATE CONSTRAINT leads_direccion_segun_titular_ck;
