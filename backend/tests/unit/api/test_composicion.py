"""La API no arma fuentes de pago mientras el tope de gasto no esté verde (tasks.md, "Qué se deja afuera")."""
from pathlib import Path

from app.composicion import registro_api
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo

FUENTES_YAML = Path(__file__).resolve().parents[3] / "config" / "fuentes.yaml"


class CromaFalsa:  # un adaptador de Croma que alguien sume al catálogo antes de que exista el tope
    pass


def test_el_registro_de_la_api_arma_las_fuentes_gratuitas_y_ninguna_de_croma():
    registro = registro_api(FUENTES_YAML, catalogo)

    assert {"osm_overpass", "datos_gov_co_rues"} <= set(registro.fuentes)
    assert [c for c, (_, meta) in registro.fuentes.items() if meta.proveedor == "croma"] == []


def test_aunque_croma_entre_al_catalogo_la_api_no_la_arma():
    con_croma = {**catalogo, "croma_supersociedades_co": CromaFalsa}

    registro = registro_api(FUENTES_YAML, con_croma)

    assert "croma_supersociedades_co" not in registro.fuentes
    assert [c for c, (_, meta) in registro.fuentes.items() if meta.proveedor == "croma"] == []
