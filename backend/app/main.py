import os
from contextlib import asynccontextmanager

import httpx
import yaml
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import db
from app.api import actividades, baja, busquedas, geografia, tablero, usuarios
from app.api.sesion import tenant_actual
from app.composicion import CONFIG, cargar_geografia, cargar_tarifas, registro_api
from app.config import SettingsApi, verificar_entorno
from app.modulos.acceso.infraestructura.verificador_jwks import VerificadorJwks, cliente_jwks
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo
from app.seguridad.cifrado import Cifrador


@asynccontextmanager
async def lifespan(app: FastAPI):
    verificar_entorno()
    app.state.settings = SettingsApi()
    app.state.engine = db.crear_engine(app.state.settings.database_url)
    db.verificar_rol(app.state.engine)
    app.state.verificador = VerificadorJwks(
        cliente_jwks(app.state.settings.auth_jwks_url), issuer=app.state.settings.auth_issuer)
    # Cada arranque re-fija lo inyectable: un test (o un arranque anterior) que lo pisó no deja rastro. La fábrica lo lee
    # de app.state en cada request.
    app.state.cifrador = Cifrador(app.state.settings.cifrado_key.get_secret_value())
    app.state.transporte_http = httpx.HTTPTransport()
    app.state.actividades_yaml = yaml.safe_load((CONFIG / "actividades.yaml").read_text()) or {}
    app.state.registro = registro_api(CONFIG / "fuentes.yaml", catalogo)
    app.state.canales_contacto = (yaml.safe_load((CONFIG / "fuentes.yaml").read_text()) or {}).get("canales_contacto") or {}
    app.state.tarifas = cargar_tarifas()
    # Un archivo por país en config/geografia/: la estructura admite MX/PE/BR sin tocar código; sin archivo, no se ofrece.
    app.state.geografia = cargar_geografia(CONFIG / "geografia")
    app.state.camaras_yaml = CONFIG / "camaras_co.yaml"
    yield


# Sin docs ni esquema públicos: no se anuncia la superficie de la API.
# Docs apagadas por defecto (sin esquema tampoco se montan /docs ni /redoc). DOCS_HABILITADAS=true las prende
# desde Railway mientras se desarrolla; el esquema no lleva secretos, pero publica el mapa de la API.
_DOCS = os.environ.get("DOCS_HABILITADAS") == "true"
app = FastAPI(lifespan=lifespan, openapi_url="/openapi.json" if _DOCS else None, redoc_url=None)
# CORS_ORIGINS no es secret: se lee acá, antes de verificar_entorno() en el lifespan.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o for o in (s.strip().rstrip("/") for s in os.environ.get("CORS_ORIGINS", "").split(",")) if o
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],  # Bearer en header; sin cookies, así que sin allow_credentials
)


@app.exception_handler(RequestValidationError)
async def _validacion(_request: Request, error: RequestValidationError):
    """422 con códigos, nunca frases ni el valor recibido: {errores: [{campo, codigo}]}."""
    errores = [{"campo": next((str(x) for x in e["loc"][1:] if isinstance(x, str)), "cuerpo"), "codigo": e["type"]}
               for e in error.errors()]
    return JSONResponse(status_code=422, content={"errores": errores})


@app.get("/health")
def health(request: Request):
    try:
        with request.app.state.engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "db": "error"})
    return {"status": "ok", "db": "ok"}


# La dependencia va en el include: una ruta nueva no puede quedar sin auth por olvido.
for _router in (busquedas.router, tablero.router, actividades.router, geografia.router, usuarios.router):
    app.include_router(_router, dependencies=[Depends(tenant_actual)])

# Pública a propósito: el enlace de baja llega por mail, sin sesión. Está en RUTAS_PUBLICAS y su test la fija.
app.include_router(baja.router)
