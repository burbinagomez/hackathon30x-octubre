from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/geografia")
def geografia(request: Request):
    """Departamentos por país (hoy solo CO) con su código DIVIPOLA. Dato de catálogo (config/departamentos_co.yaml)."""
    return {
        pais: [{"codigo": str(codigo), "nombre_es": e["nombre_es"], "nombre_en": e["nombre_en"]}
               for codigo, e in sorted(departamentos.items(), key=lambda kv: str(kv[0]))]
        for pais, departamentos in request.app.state.departamentos_yaml.items()
    }
