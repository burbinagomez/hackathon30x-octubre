from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import SecretProhibido


def crear_engine(url):
    # Supavisor en modo transacción no soporta prepared statements; None = psycopg no prepara nunca (R10).
    return create_engine(url, connect_args={"prepare_threshold": None})


def verificar_rol(engine):
    """Corta el arranque si DATABASE_URL entra con un rol que saltea RLS, se llame como se llame."""
    try:
        with engine.connect() as conexion:
            saltea_rls = conexion.execute(text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )).scalar()
    except OperationalError:
        # ponytail: con la base caída al arrancar no se chequea (/health da 503); si pasa, mover a un evento "connect".
        return
    if saltea_rls:
        raise SecretProhibido("DATABASE_URL entra con un rol que saltea RLS")
