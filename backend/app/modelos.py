from sqlalchemy import MetaData

# Sin importar config: el drift check (test_migraciones) lo carga sin el entorno de api.
metadata = MetaData()
