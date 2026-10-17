import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import db
from app.config import Settings, verificar_entorno


@asynccontextmanager
async def lifespan(app: FastAPI):
    verificar_entorno()
    app.state.settings = Settings()
    app.state.engine = db.crear_engine(app.state.settings.database_url)
    db.verificar_rol(app.state.engine)
    yield


app = FastAPI(lifespan=lifespan)
# CORS_ORIGINS no es secret: se lee acá, antes de verificar_entorno() en el lifespan.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o for o in (s.strip().rstrip("/") for s in os.environ.get("CORS_ORIGINS", "").split(",")) if o
    ],
)


@app.get("/health")
def health():
    try:
        with app.state.engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "db": "error"})
    return {"status": "ok", "db": "ok"}
