from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


@router.get("/geografia")
def geografia(request: Request, pais: str | None = Query(default=None, pattern=r"^[A-Z]{2}$")):
    """Sin `pais`: los países que tienen archivo en config/geografia/. Con `pais`: sus divisiones (código común ISO 3166-2,
    código nativo y nombres es/en) y los municipios de cada una. Dato de catálogo; la API manda códigos, el front elige idioma."""
    archivos = request.app.state.geografia
    if pais is None:
        return {"paises": sorted(archivos)}
    if pais not in archivos:
        raise HTTPException(status_code=404, detail="pais_sin_geografia")
    return {"pais": pais, "divisiones": sorted(archivos[pais]["divisiones"], key=lambda d: str(d["codigo_nativo"]))}
