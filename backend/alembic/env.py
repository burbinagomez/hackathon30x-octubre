import os

from alembic import context
from sqlalchemy import create_engine, text

from app.modelos import metadata

# Desacoplado de app.config: el job de migraciones no tiene el entorno de api, y api nunca ve esta URL.
engine = create_engine(os.environ["MIGRATION_DATABASE_URL"])

with engine.connect() as conexion:
    # Fija el esquema aunque PGOPTIONS o el rol cambien el search_path: alembic_version y el drift miran solo public.
    conexion.execute(text("SET search_path TO public, extensions"))
    conexion.commit()
    context.configure(connection=conexion, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
