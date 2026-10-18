"""Siembra (o actualiza) el tenant del evento. Corre un humano desde local; la URL de postgres va por getpass.

uv run python scripts/sembrar_tenant.py --nombre "Evento" [--id UUID] [--idioma es|en]
"""
import argparse
import getpass
import sys
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def sembrar(conexion, tenant_id: UUID, nombre: str, idioma: str) -> None:
    conexion.execute(
        text("INSERT INTO tenants (id, nombre, idioma) VALUES (:id, :nombre, :idioma) "
             "ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, idioma = EXCLUDED.idioma"),
        {"id": tenant_id, "nombre": nombre, "idioma": idioma},
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Siembra el tenant del evento (pide la URL de postgres por getpass).")
    p.add_argument("--id", type=UUID, default=None)
    p.add_argument("--nombre", required=True)
    p.add_argument("--idioma", choices=["es", "en"], default="es")
    args = p.parse_args(argv)
    tenant_id = args.id or uuid4()
    try:
        url = make_url(getpass.getpass("URL de postgres (no se muestra): ")).set(drivername="postgresql+psycopg")
        engine = create_engine(url)
        try:
            with engine.begin() as c:
                sembrar(c, tenant_id, args.nombre, args.idioma)
        finally:
            engine.dispose()
    except Exception as e:  # el mensaje de la excepción puede traer la URL: solo el tipo
        print(f"no se pudo sembrar el tenant ({type(e).__name__})", file=sys.stderr)
        return 1
    print(tenant_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
