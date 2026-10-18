from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.exc import OperationalError

from app.config import SecretProhibido


@contextmanager
def unidad_de_trabajo(engine: Engine, tenant_id: UUID) -> Iterator[Connection]:
    """Una transacción con el tenant fijado como primera sentencia; commit al salir, rollback si lanza.

    set_config(..., true) = SET LOCAL: muere con la transacción. Nunca de sesión: el pooler en modo
    transacción le pasa la conexión a otro cliente.
    """
    with engine.begin() as conexion:
        conexion.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": str(tenant_id)})
        yield conexion


def crear_engine(url):
    # Supavisor en modo transacción no soporta prepared statements; None = psycopg no prepara nunca (R10).
    # hide_parameters: el "[parameters: …]" de SQLAlchemy lleva nombre y dirección de los leads (principio VI).
    engine = create_engine(url, connect_args={"prepare_threshold": None}, hide_parameters=True)
    event.listen(engine, "first_connect", _verificar_rol)
    return engine


def _verificar_rol(conexion_dbapi, _registro):
    """Frena la primera conexión real si DATABASE_URL entra con un rol que saltea RLS, se llame como se llame.

    first_connect corre una vez por engine, pero se reintenta si falla: un rol peligroso no conecta nunca.
    """
    with conexion_dbapi.cursor() as cursor:
        cursor.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        saltea_rls = cursor.fetchone()[0]
    conexion_dbapi.rollback()
    if saltea_rls:
        raise SecretProhibido("DATABASE_URL entra con un rol que saltea RLS")


def verificar_rol(engine):
    """Al arrancar, fuerza la primera conexión para que un rol peligroso corte el arranque ya."""
    try:
        engine.connect().close()
    except OperationalError:
        return  # base caída: /health da 503 y el chequeo corre en la primera conexión real
