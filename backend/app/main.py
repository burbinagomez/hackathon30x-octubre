from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, verificar_entorno


@asynccontextmanager
async def lifespan(app: FastAPI):
    verificar_entorno()
    app.state.settings = Settings()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
