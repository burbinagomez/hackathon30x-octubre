from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError

from app.config import SecretProhibido


def crear_engine(url):
    # Supavisor en modo transacción no soporta prepared statements; None = psycopg no prepara nunca (R10).
    engine = create_engine(url, connect_args={"prepare_threshold": None})
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
