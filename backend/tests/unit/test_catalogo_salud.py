"""Salud en el catálogo: "software para hospitales" tiene que encontrar actividad, no repreguntar (QA 2026-10-18)."""
from pathlib import Path

import yaml

CATALOGO = yaml.safe_load((Path(__file__).parents[2] / "config" / "actividades.yaml").read_text(encoding="utf-8"))
PROMPT = (Path(__file__).parents[2] / "app/modulos/intake/infraestructura/llm/frase_a_icp_v2.md").read_text(encoding="utf-8")


def test_hospitales_clinicas_y_apoyo_diagnostico_estan_en_el_catalogo():
    assert {"8610", "8621", "8691", "8692", "8699"} <= set(CATALOGO)
    assert "amenity=hospital" in CATALOGO["8610"]["osm"]


def test_el_prompt_no_repregunta_si_el_comprador_ya_esta_dicho():
    assert '"software para hospitales"' in PROMPT
    assert "no está en la lista, NO preguntes" in PROMPT


def test_el_prompt_pregunta_la_ubicacion_si_falta():
    # Sin departamento ni ciudad ninguna fuente corre: mejor preguntar que dejar Buscar gris (QA 2026-10-18).
    assert "¿En qué ciudad o departamento buscamos?" in PROMPT
