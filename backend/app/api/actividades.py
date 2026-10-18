from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/actividades")
def listar_actividades(request: Request):
    """Dato de catálogo (config/actividades.yaml), no texto de la API. `nombre_en` va siempre, con null si falta."""
    entradas = request.app.state.actividades_yaml
    return [{"codigo": str(codigo), "nombre_es": e["nombre_es"], "nombre_en": e.get("nombre_en")}
            for codigo, e in sorted(entradas.items(), key=lambda kv: str(kv[0]))]
