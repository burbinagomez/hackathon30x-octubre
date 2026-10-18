"""Alta de un usuario: inserta su fila en `usuarios` (auth_user_id + tenant). Corre un humano desde local.

El usuario de Supabase lo crea el dueño en el panel (Authentication > Users); su id es el `auth_user_id`.
La URL de postgres va por getpass, nunca por argumento ni por entorno.

uv run python scripts/crear_usuario.py --auth-user-id UUID --tenant UUID [--idioma es|en]

Procedimiento de baja: borrar la fila de `usuarios` (`DELETE FROM usuarios WHERE auth_user_id = ...`). Desde ese
momento `tenant_de_usuario` devuelve 0 filas y el token deja de servir aunque no haya vencido. La cuenta de
Supabase se deshabilita aparte, en el panel (paso humano).
"""
import argparse
import getpass
import sys
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def crear(conexion, auth_user_id: UUID, tenant_id: UUID, idioma: str | None) -> None:
    # INSERT a secas: repetir un usuario falla en vez de moverlo de tenant en silencio.
    conexion.execute(
        text("INSERT INTO usuarios (auth_user_id, tenant_id, idioma) VALUES (:u, :t, :idioma)"),
        {"u": auth_user_id, "t": tenant_id, "idioma": idioma},
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Da de alta la fila de usuarios (pide la URL de postgres por getpass).")
    p.add_argument("--auth-user-id", type=UUID, required=True)
    p.add_argument("--tenant", type=UUID, required=True)
    p.add_argument("--idioma", choices=["es", "en"], default=None)
    args = p.parse_args(argv)
    try:
        url = make_url(getpass.getpass("URL de postgres (no se muestra): ")).set(drivername="postgresql+psycopg")
        engine = create_engine(url)
        try:
            with engine.begin() as c:
                crear(c, args.auth_user_id, args.tenant, args.idioma)
        finally:
            engine.dispose()
    except Exception as e:  # el mensaje de la excepción puede traer la URL: solo el tipo
        print(f"no se pudo crear el usuario ({type(e).__name__})", file=sys.stderr)
        return 1
    print(args.auth_user_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
