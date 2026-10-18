# Único lugar que nombra clases concretas de adaptadores. clave de fuentes.yaml -> clase.
from app.modulos.descubrimiento.infraestructura.adaptadores.croma_supersociedades import (
    CromaSupersociedadesCo,
)
from app.modulos.descubrimiento.infraestructura.adaptadores.datos_gov_co_rues import (
    DatosGovCoRues,
)
from app.modulos.descubrimiento.infraestructura.adaptadores.osm_overpass import (
    OsmOverpass,
)

catalogo: dict[str, type] = {
    "croma_supersociedades_co": CromaSupersociedadesCo,
    "datos_gov_co_rues": DatosGovCoRues,
    "osm_overpass": OsmOverpass,
}
