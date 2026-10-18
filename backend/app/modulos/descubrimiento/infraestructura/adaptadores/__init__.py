# Único lugar que nombra clases concretas de adaptadores. clave de fuentes.yaml -> clase.
from app.modulos.descubrimiento.infraestructura.adaptadores.osm_overpass import OsmOverpass

catalogo: dict[str, type] = {
    "osm_overpass": OsmOverpass,
}
