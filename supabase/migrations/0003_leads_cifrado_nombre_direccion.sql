-- 0003: nombre y dirección cifrados para titulares no jurídicos. SQL a mano. Corre como postgres (dueño).
-- Jurídica: nombre y direccion en claro. Cualquier otro tipo_titular: solo nombre_cifrado / direccion_cifrada.
-- El cifrado lo hace la app (AES-GCM, CIFRADO_KEY); SQL no cifra nada.

ALTER TABLE public.leads
  ADD COLUMN nombre_cifrado    bytea,
  ADD COLUMN direccion_cifrada bytea;

-- Un lead no jurídico no tiene nombre en claro.
ALTER TABLE public.leads ALTER COLUMN nombre DROP NOT NULL;
