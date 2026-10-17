import shutil
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
CONTRATO = "Fuentes prohibidas"


def lint_imports(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["lint-imports", "--no-cache", "--config", str(cwd / "pyproject.toml")],
        cwd=cwd, capture_output=True, text=True,
    )


def test_detecta_import_prohibido(tmp_path):
    # El canario usa la config real: si alguien afloja el contrato, este test lo ve.
    shutil.copy(BACKEND / "pyproject.toml", tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("import googlemaps\n")

    r = lint_imports(tmp_path)

    assert r.returncode != 0
    assert f"{CONTRATO} BROKEN" in r.stdout


def test_repo_cumple_contratos():
    r = lint_imports(BACKEND)
    assert r.returncode == 0, r.stdout + r.stderr
