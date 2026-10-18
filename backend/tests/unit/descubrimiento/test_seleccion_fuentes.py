from pathlib import Path

import pytest

from app.modulos.descubrimiento.aplicacion.registro import cargar_actividades, cargar_registro
from app.modulos.descubrimiento.dominio.errores import CriterioNoSoportado
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente, PaginaEmpresas
from app.modulos.descubrimiento.dominio.seleccion import seleccionar_fuentes

CONFIG = Path(__file__).resolve().parents[3] / "config"
ACTIVIDADES_YAML = CONFIG / "actividades.yaml"
SUPERSOCIEDADES = "croma_supersociedades_co"
OSM = "osm_overpass"


@pytest.fixture
def metas() -> list[MetaFuente]:
    # Las MetaFuente del fuentes.yaml real; el catálogo falso solo dice qué claves están implementadas.
    registro = cargar_registro(CONFIG / "fuentes.yaml", {SUPERSOCIEDADES: object, OSM: object})
    return [m for _, m in registro.fuentes.values()]


@pytest.fixture
def actividades() -> dict[str, tuple[str, ...]]:
    return cargar_actividades(ACTIVIDADES_YAML)


def test_actividades_yaml_real_carga_y_mapea_4711():
    actividades = cargar_actividades(ACTIVIDADES_YAML)

    assert set(actividades.get("4711", ())) == {"shop=supermarket", "shop=convenience"}


def test_icp_colombia_completo_usa_las_dos_fuentes(metas, actividades):
    icp = CriteriosICP("CO", {"ciiu": "4711", "departamento": "11", "ciudad": "Bogotá"})

    seleccionadas, ignoradas = seleccionar_fuentes(metas, icp, actividades)

    assert seleccionadas.keys() == {SUPERSOCIEDADES, OSM}
    assert ignoradas == {}
    assert dict(seleccionadas[SUPERSOCIEDADES].filtros) == {"ciiu": "4711", "departamento": "11"}
    assert dict(seleccionadas[OSM].filtros) == {
        "ciudad": "Bogotá",
        "tipo_negocio": ("shop=supermarket", "shop=convenience"),
    }
    assert seleccionadas[OSM].pais == seleccionadas[SUPERSOCIEDADES].pais == "CO"


def test_icp_sin_ciudad_ignora_osm_por_geografia(metas, actividades):
    icp = CriteriosICP("CO", {"ciiu": "4711", "departamento": "11"})

    seleccionadas, ignoradas = seleccionar_fuentes(metas, icp, actividades)

    assert ignoradas == {OSM: "sin_geografia"}
    assert set(seleccionadas) == {SUPERSOCIEDADES}


def test_ciiu_sin_mapeo_ignora_osm(metas, actividades):
    assert "9999" not in actividades
    icp = CriteriosICP("CO", {"ciiu": "9999", "departamento": "11", "ciudad": "Bogotá"})

    seleccionadas, ignoradas = seleccionar_fuentes(metas, icp, actividades)

    assert ignoradas == {OSM: "sin_mapeo_actividad"}
    assert set(seleccionadas) == {SUPERSOCIEDADES}


@pytest.mark.parametrize("pais", ["BR", "PE"])
def test_icp_fuera_de_colombia_solo_usa_osm(metas, actividades, pais):
    icp = CriteriosICP(pais, {"ciiu": "4711", "ciudad": "Ciudad Ficticia"})

    seleccionadas, ignoradas = seleccionar_fuentes(metas, icp, actividades)

    assert seleccionadas.keys() == {OSM}
    assert ignoradas == {SUPERSOCIEDADES: "pais"}


class _FuenteFalsa:
    """Como el contrato del 002: un criterio que no declara es CriterioNoSoportado."""

    def __init__(self, meta: MetaFuente):
        self.meta = meta
        self.recibidos: list[CriteriosICP] = []

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        sobrantes = set(criterios.filtros) - self.meta.filtros
        if sobrantes:
            raise CriterioNoSoportado(f"{self.meta.clave}: {sorted(sobrantes)}")
        self.recibidos.append(criterios)
        return PaginaEmpresas((), None)


def test_criterio_no_declarado_no_llega_al_adaptador(metas, actividades):
    icp = CriteriosICP(
        "CO", {"ciiu": "4711", "departamento": "11", "ciudad": "Bogotá", "ingresos_min": "1000000000"}
    )
    fuentes = {m.clave: _FuenteFalsa(m) for m in metas}

    seleccionadas, _ = seleccionar_fuentes(metas, icp, actividades)
    for clave, criterios in seleccionadas.items():
        fuentes[clave].buscar(criterios, 1)

    assert seleccionadas.keys() == {SUPERSOCIEDADES, OSM}
    assert fuentes[SUPERSOCIEDADES].recibidos[0].filtros["ingresos_min"] == "1000000000"
    assert len(fuentes[OSM].recibidos) == 1
    assert "ingresos_min" not in fuentes[OSM].recibidos[0].filtros


def test_datos_gov_co_habilitada_recibe_ciiu_y_departamento():
    meta = MetaFuente(
        clave="datos_gov_co_rues", proveedor="datos.gov.co", paises=frozenset({"CO"}),
        filtros=frozenset({"ciiu", "departamento"}), trae=frozenset({"nit"}), tipo="dataset", licencia="CC-BY-SA-4.0",
    )
    icp = CriteriosICP("CO", {"ciiu": "4711", "departamento": "11", "ingresos_min": "1"})

    seleccionadas, ignoradas = seleccionar_fuentes([meta], icp, {})

    assert ignoradas == {}
    assert dict(seleccionadas["datos_gov_co_rues"].filtros) == {"ciiu": "4711", "departamento": "11"}
