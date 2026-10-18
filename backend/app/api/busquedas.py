from fastapi import APIRouter

from app.api._501 import sin_implementar

router = APIRouter()
router.add_api_route("/busquedas/vista-previa", sin_implementar, methods=["POST"])  # esqueleto T004
router.add_api_route("/busquedas/{busqueda_id}/ejecutar", sin_implementar, methods=["POST"])
