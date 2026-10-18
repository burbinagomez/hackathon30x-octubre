"""La carga de config/geografia/*.yaml: un país, un archivo."""
from pathlib import Path

import pytest

from app.composicion import CONFIG, cargar_geografia


def test_carga_un_pais_por_archivo_con_su_clave():
    geografia = cargar_geografia(CONFIG / "geografia")
    assert set(geografia) == {"CO"}
    assert len(geografia["CO"]["divisiones"]) == 33


def test_dos_archivos_con_el_mismo_pais_impiden_arrancar(tmp_path: Path):
    for nombre in ("co.yaml", "co_copia.yaml"):
        (tmp_path / nombre).write_text("pais: CO\ndivisiones: []\n")

    with pytest.raises(ValueError, match="CO"):  # sin esto el segundo archivo pisa al primero en silencio
        cargar_geografia(tmp_path)


def test_un_archivo_sin_pais_impide_arrancar(tmp_path: Path):
    (tmp_path / "x.yaml").write_text("divisiones: []\n")
    with pytest.raises(ValueError):
        cargar_geografia(tmp_path)
