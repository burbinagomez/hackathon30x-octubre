from fastapi import APIRouter

from app.api._501 import sin_implementar

router = APIRouter()
router.add_api_route("/tablero/fuentes", sin_implementar, methods=["GET"])  # esqueleto T004
