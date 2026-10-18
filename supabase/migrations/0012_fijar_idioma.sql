-- 0012: fijar_idioma [Pulido]. SQL a mano. Corre como postgres (dueño). Va después de la 0011.
-- El usuario cambia su idioma sin que app_rt toque usuarios: la tabla no da UPDATE al rol de runtime
-- (0006), así que el UPDATE va por función SECURITY DEFINER, con el mismo patrón que tenant_de_usuario.
-- DDL aprobado en specs/012-seguridad/plan.md §E4 (allí numerado 0007; aquí la 0007 ya es de calificaciones).

-- El tenant NO sale del body ni del token: sale de app.tenant_id, que la api ya seteó al resolver la sesión
-- (tenant_de_usuario). current_setting sin missing_ok: sin tenant seteado la función falla en vez de
-- actualizar sin filtro. RETURNS integer para que la ruta distinga 1 fila de 0 sin un SELECT extra.
CREATE FUNCTION public.fijar_idioma(p_auth_user_id uuid, p_idioma text)
  RETURNS integer
  LANGUAGE plpgsql VOLATILE SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
DECLARE
  filas integer;
BEGIN
  UPDATE public.usuarios
     SET idioma = p_idioma
   WHERE auth_user_id = p_auth_user_id
     AND tenant_id = current_setting('app.tenant_id')::uuid;
  GET DIAGNOSTICS filas = ROW_COUNT;
  RETURN filas;
END
$$;

REVOKE ALL ON FUNCTION public.fijar_idioma(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.fijar_idioma(uuid, text) TO app_rt;

-- Roles de Supabase: la 0006 ya revocó el default de PUBLIC y el de anon/authenticated para lo que cree
-- postgres, pero el REVOKE explícito deja la función cerrada aunque el default cambie. Solo si existen
-- (en vanilla no hay nada que revocar).
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON FUNCTION public.fijar_idioma(uuid, text) FROM anon, authenticated;
  END IF;
END
$$;
