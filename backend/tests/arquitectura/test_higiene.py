from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
MAXIMO = 100


def _lineas(ruta: Path) -> int:
    return len(ruta.read_text().splitlines())


def test_detecta_claude_md_que_excede_el_maximo(tmp_path):
    archivo = tmp_path / "CLAUDE.md"
    archivo.write_text("\n".join(f"linea {i}" for i in range(101)))
    assert _lineas(archivo) > MAXIMO


def test_claude_md_del_repo_no_excede_el_maximo():
    # Un solo CLAUDE.md raíz + opcionales en backend/ y frontend/ (constitución, doc viva).
    candidatos = [RAIZ / "CLAUDE.md", RAIZ / "backend" / "CLAUDE.md", RAIZ / "frontend" / "CLAUDE.md"]
    for ruta in candidatos:
        if ruta.exists():
            assert _lineas(ruta) <= MAXIMO, f"{ruta} supera {MAXIMO} líneas"
