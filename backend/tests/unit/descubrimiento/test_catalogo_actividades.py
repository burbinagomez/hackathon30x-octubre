"""Integridad de config/actividades.yaml: el catálogo que alimenta GET /actividades y el mapeo CIIU -> OSM."""
import re
from pathlib import Path

import yaml

RUTA = Path(__file__).resolve().parents[3] / "config" / "actividades.yaml"
CLAVES_OSM = {"shop", "amenity", "office", "craft", "tourism", "leisure", "healthcare"}
ETIQUETA = re.compile(r"^([a-z_]+)=([a-z0-9_]+)$")


def _crudo() -> list[str]:
    return [l.split(":")[0].strip('"') for l in RUTA.read_text().splitlines() if re.match(r'^"?\d', l)]


def _entradas() -> dict:
    return yaml.safe_load(RUTA.read_text())


def test_catalogo_tiene_al_menos_20_actividades():
    assert len(_entradas()) >= 20


def test_claves_son_ciiu_de_4_digitos_y_no_se_repiten():
    crudo = _crudo()
    assert len(crudo) == len(set(crudo)), "claves duplicadas en el YAML"
    assert len(crudo) == len(_entradas())
    assert [k for k in _entradas() if not re.fullmatch(r"\d{4}", str(k))] == []


def test_todas_tienen_nombre_es_y_nombre_en():
    e = _entradas()
    assert [k for k, v in e.items() if not (v.get("nombre_es") or "").strip()] == []
    assert [k for k, v in e.items() if not (v.get("nombre_en") or "").strip()] == []


def test_etiquetas_osm_son_clave_valor_con_clave_en_lista_blanca():
    malas = []
    for k, v in _entradas().items():
        for et in v.get("osm") or []:
            m = ETIQUETA.match(et)
            if not m or m.group(1) not in CLAVES_OSM:
                malas.append((k, et))
    assert malas == []


def test_no_hay_etiquetas_osm_repetidas_dentro_de_una_actividad():
    assert [k for k, v in _entradas().items() if len(v.get("osm") or []) != len(set(v.get("osm") or []))] == []
