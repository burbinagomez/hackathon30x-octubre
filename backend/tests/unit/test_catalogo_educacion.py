"""Educación (CIIU Rev. 4 A.C., división 85) en config/actividades.yaml: nombres oficiales y mapeo OSM acotado."""
from pathlib import Path

import yaml

CATALOGO = yaml.safe_load((Path(__file__).parents[2] / "config" / "actividades.yaml").read_text())
EDUCACION = ["8511", "8512", "8513", "8521", "8522", "8523", "8530", "8541", "8542", "8543", "8544", "8551", "8552", "8553",
             "8559"]


def test_estan_los_15_ciiu_de_educacion_con_nombre_es_y_en():
    for codigo in EDUCACION:
        assert CATALOGO[codigo]["nombre_es"] and CATALOGO[codigo]["nombre_en"], codigo


def test_el_nombre_oficial_de_secundaria_y_el_mapeo_osm():
    assert CATALOGO["8521"]["nombre_es"] == "Educación básica secundaria"
    assert CATALOGO["8521"]["osm"] == ["amenity=school"]
    assert CATALOGO["8544"]["osm"] == ["amenity=university"]
    assert CATALOGO["8512"]["osm"] == ["amenity=kindergarten"]
    assert "osm" not in CATALOGO["8551"]
