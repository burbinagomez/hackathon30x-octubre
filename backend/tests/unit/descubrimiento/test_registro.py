from pathlib import Path

import pytest
import yaml

from app.modulos.descubrimiento.aplicacion.registro import cargar_registro
from app.modulos.descubrimiento.dominio.errores import RegistroInvalido
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo

ROJO_T040 = pytest.mark.xfail(strict=True, raises=AssertionError, reason="rojo T038/T043; verde en T040")

FUENTES_YAML = Path(__file__).resolve().parents[3] / "config" / "fuentes.yaml"


class Falsa:
    pass


def _yaml(tmp_path: Path, contenido: str) -> Path:
    ruta = tmp_path / "fuentes.yaml"
    ruta.write_text(contenido)
    return ruta


ENTRADA = """
    proveedor: x
    tipo: dataset
    paises: [CO]
    filtros: [ciiu]
    trae: [nit]
    licencia: l
"""


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="rojo hasta T031: el catálogo todavía no tiene croma_supersociedades_co")
def test_carga_config_fuentes_yaml_real_sin_error():
    registro = cargar_registro(FUENTES_YAML, catalogo)
    assert set(registro.fuentes) == {"croma_supersociedades_co"}
    assert registro.sin_implementacion == {"croma_dian_trade_co", "osm_overpass"}


def test_solo_carga_adaptadores_habilitados(tmp_path):
    ruta = _yaml(
        tmp_path,
        "fuentes_descubrimiento:\n"
        f"  a:\n    habilitado: true{ENTRADA}"
        f"  b:\n    habilitado: false{ENTRADA}",
    )
    registro = cargar_registro(ruta, {"a": Falsa, "b": Falsa})
    assert set(registro.fuentes) == {"a"}
    clase, meta = registro.fuentes["a"]
    assert clase is Falsa
    assert meta.clave == "a"
    assert meta.paises == {"CO"}
    assert meta.filtros == {"ciiu"}


def test_habilitado_sin_implementacion_se_reporta(tmp_path):
    ruta = _yaml(
        tmp_path,
        "fuentes_descubrimiento:\n"
        f"  a:\n    habilitado: true{ENTRADA}"
        f"  sin_clase:\n    habilitado: true{ENTRADA}",
    )
    registro = cargar_registro(ruta, {"a": Falsa})
    assert set(registro.fuentes) == {"a"}
    assert registro.sin_implementacion == {"sin_clase"}


@pytest.mark.parametrize("falta", ["paises", "filtros"])
def test_fuente_habilitada_sin_paises_o_filtros_falla(tmp_path, falta):
    entrada = "".join(l + "\n" for l in ENTRADA.splitlines() if l and falta not in l)
    ruta = _yaml(
        tmp_path,
        "fuentes_descubrimiento:\n"
        f"  a:\n    habilitado: true\n{entrada}"
        # deshabilitada e incompleta: no se valida
        "  b:\n    habilitado: false\n",
    )
    with pytest.raises(RegistroInvalido):
        cargar_registro(ruta, {"a": Falsa})


def test_deshabilitada_incompleta_no_se_valida(tmp_path):
    ruta = _yaml(
        tmp_path,
        "fuentes_descubrimiento:\n"
        f"  a:\n    habilitado: true{ENTRADA}"
        "  b:\n    habilitado: false\n",
    )
    assert set(cargar_registro(ruta, {"a": Falsa}).fuentes) == {"a"}


def test_clave_del_catalogo_ausente_del_yaml_falla(tmp_path):
    ruta = _yaml(tmp_path, f"fuentes_descubrimiento:\n  a:\n    habilitado: true{ENTRADA}")
    with pytest.raises(RegistroInvalido):
        cargar_registro(ruta, {"a": Falsa, "fantasma": Falsa})


def test_osm_overpass_carga_con_el_catalogo_real():
    registro = cargar_registro(FUENTES_YAML, catalogo)
    assert "osm_overpass" in registro.fuentes
    assert "osm_overpass" not in registro.sin_implementacion


@ROJO_T040
def test_datos_gov_co_rues_del_yaml_real_se_carga():
    """Conectada por config (`habilitado: true`): cargada, con implementación y con el dataset de la spec."""
    registro = cargar_registro(FUENTES_YAML, catalogo)
    entrada = yaml.safe_load(FUENTES_YAML.read_text())["fuentes_descubrimiento"]["datos_gov_co_rues"]

    assert "datos_gov_co_rues" in registro.fuentes
    assert "datos_gov_co_rues" not in registro.sin_implementacion
    assert entrada["dataset"] == "c82u-588k"
    assert entrada["filtros"] == ["ciiu", "departamento"]
    assert entrada["licencia"] == "CC-BY-SA-4.0"
