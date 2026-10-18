import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import db
from app.api import actividades, busquedas, tablero, usuarios
from app.api.sesion import tenant_actual
from app.config import Settings, verificar_entorno
from app.modulos.acceso.infraestructura.verificador_jwks import VerificadorJwks, cliente_jwks


@asynccontextmanager
async def lifespan(app: FastAPI):
    verificar_entorno()
    app.state.settings = Settings()
    app.state.engine = db.crear_engine(app.state.settings.database_url)
    db.verificar_rol(app.state.engine)
    app.state.verificador = VerificadorJwks(
        cliente_jwks(app.state.settings.auth_jwks_url), issuer=app.state.settings.auth_issuer)
    yield


# Sin docs ni esquema públicos: no se anuncia la superficie de la API.
app = FastAPI(lifespan=lifespan, openapi_url=None)  # sin esquema tampoco se montan /docs ni /redoc
# CORS_ORIGINS no es secret: se lee acá, antes de verificar_entorno() en el lifespan.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o for o in (s.strip().rstrip("/") for s in os.environ.get("CORS_ORIGINS", "").split(",")) if o
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],  # Bearer en header; sin cookies, así que sin allow_credentials
)


@app.get("/health")
def health(request: Request):
    try:
        with request.app.state.engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "db": "error"})
    return {"status": "ok", "db": "ok"}


# La dependencia va en el include: una ruta nueva no puede quedar sin auth por olvido.
for _router in (busquedas.router, tablero.router, actividades.router, usuarios.router):
    app.include_router(_router, dependencies=[Depends(tenant_actual)])
