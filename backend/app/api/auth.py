from fastapi import APIRouter

from app.api._501 import sin_implementar

router = APIRouter()
router.add_api_route("/auth/sesion", sin_implementar, methods=["POST"])  # esqueleto T004
