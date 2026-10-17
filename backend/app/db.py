from sqlalchemy import create_engine


def crear_engine(url):
    # Supavisor en modo transacción no soporta prepared statements; None = psycopg no prepara nunca (R10).
    return create_engine(url, connect_args={"prepare_threshold": None})
