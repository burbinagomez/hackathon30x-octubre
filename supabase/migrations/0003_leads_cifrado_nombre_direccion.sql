-- 0003: nombre y dirección cifrados para titulares no jurídicos. SQL a mano. Corre como postgres (dueño).
-- Jurídica: nombre y direccion en claro. Cualquier otro tipo_titular: solo nombre_cifrado / direccion_cifrada.
-- El cifrado lo hace la app (AES-GCM, CIFRADO_KEY); SQL no cifra nada.

ALTER TABLE public.leads
  ADD COLUMN nombre_cifrado    bytea,
  ADD COLUMN direccion_cifrada bytea;

-- Un lead no jurídico no tiene nombre en claro.
ALTER TABLE public.leads ALTER COLUMN nombre DROP NOT NULL;

-- octet_length > 28: nonce de 12 bytes + etiqueta GCM de 16; un bytea más corto no es un cifrado.
-- NOT VALID: las filas ya guardadas (leads OSM del [MIN], en claro) no se pueden cifrar desde SQL.
ALTER TABLE public.leads
  ADD CONSTRAINT leads_nombre_segun_titular_ck CHECK (
    (tipo_titular =  'juridica' AND nombre IS NOT NULL AND nombre_cifrado IS NULL)
    OR
    (tipo_titular <> 'juridica' AND nombre IS NULL
       AND nombre_cifrado IS NOT NULL AND octet_length(nombre_cifrado) > 28)
  ) NOT VALID,
  ADD CONSTRAINT leads_direccion_segun_titular_ck CHECK (
    (tipo_titular =  'juridica' AND direccion_cifrada IS NULL)
    OR
    (tipo_titular <> 'juridica' AND direccion IS NULL
       AND (direccion_cifrada IS NULL OR octet_length(direccion_cifrada) > 28))
  ) NOT VALID;

-- Intenta convalidar. En una base vacía (CI, local, prod nueva) no hay filas y los CHECK quedan
-- convalidated = true. Con filas viejas en claro falla con check_violation: se avisa (sin datos) y
-- queda NOT VALID hasta el backfill (T056) y la migración de validación. Un bloque por CHECK: si el
-- segundo falla, el primero no se deshace.
DO $$
BEGIN
  ALTER TABLE public.leads VALIDATE CONSTRAINT leads_nombre_segun_titular_ck;
EXCEPTION WHEN check_violation THEN
  RAISE NOTICE 'leads_nombre_segun_titular_ck queda NOT VALID: hay leads no juridicos en claro; correr el backfill y la migracion de validacion';
END
$$;

DO $$
BEGIN
  ALTER TABLE public.leads VALIDATE CONSTRAINT leads_direccion_segun_titular_ck;
EXCEPTION WHEN check_violation THEN
  RAISE NOTICE 'leads_direccion_segun_titular_ck queda NOT VALID: hay leads no juridicos en claro; correr el backfill y la migracion de validacion';
END
$$;

-- Sin GRANT/REVOKE nuevos: app_rt ya tiene SELECT, INSERT, UPDATE, DELETE sobre public.leads (0002) y los
-- privilegios de tabla cubren las columnas nuevas. RLS no cambia: leads ya tiene ENABLE ROW LEVEL SECURITY
-- y la política tenant_aislado (0002); no hay tabla nueva.
