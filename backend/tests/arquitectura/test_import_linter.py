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
    # Con el árbol de app.modulos: sin los containers de layers, lint-imports falla por config.
    _arbol_modulos(tmp_path, "app/__init__.py", "import googlemaps\n")

    r = lint_imports(tmp_path)

    assert r.returncode != 0
    assert f"{CONTRATO} BROKEN" in r.stdout


CAPAS = "Capas de los modulos"
SIN_COSTOS_INFRA = "Descubrimiento no usa la infraestructura de costos"


def _arbol_modulos(raiz: Path, archivo: str, contenido: str) -> None:
    # Réplica mínima de app.modulos, con la config real copiada al lado.
    shutil.copy(BACKEND / "pyproject.toml", raiz)
    paquetes = ["app", "app/modulos",
                "app/modulos/descubrimiento", "app/modulos/costos", "app/modulos/acceso", "app/modulos/enriquecimiento",
                *(f"app/modulos/descubrimiento/{c}" for c in ("dominio", "aplicacion", "infraestructura")),
                *(f"app/modulos/costos/{c}" for c in ("dominio", "infraestructura")),
                *(f"app/modulos/acceso/{c}" for c in ("dominio", "infraestructura")),
                *(f"app/modulos/enriquecimiento/{c}" for c in ("dominio", "infraestructura"))]
    for p in paquetes:
        (raiz / p).mkdir(parents=True, exist_ok=True)
        (raiz / p / "__init__.py").touch()
    (raiz / archivo).write_text(contenido)


def test_detecta_violacion_de_capas(tmp_path):
    _arbol_modulos(tmp_path, "app/modulos/descubrimiento/dominio/x.py",
                   "import app.modulos.descubrimiento.infraestructura\n")

    r = lint_imports(tmp_path)

    assert r.returncode != 0
    assert f"{CAPAS} BROKEN" in r.stdout


def test_descubrimiento_no_importa_costos_infraestructura(tmp_path):
    # Desde infraestructura de descubrimiento: layers no lo ve (otro container), solo el forbidden.
    _arbol_modulos(tmp_path, "app/modulos/descubrimiento/infraestructura/x.py",
                   "import app.modulos.costos.infraestructura\n")

    r = lint_imports(tmp_path)

    assert r.returncode != 0
    assert f"{SIN_COSTOS_INFRA} BROKEN" in r.stdout


def test_cryptography_no_entra_al_dominio(tmp_path):
    # El cifrado es un adaptador: el dominio maneja texto en claro y nunca ve la librería (principio I).
    _arbol_modulos(tmp_path, "app/modulos/descubrimiento/dominio/x.py", "import cryptography\n")

    r = lint_imports(tmp_path)

    assert r.returncode != 0
    assert "Cifrado fuera del dominio BROKEN" in r.stdout


SIN_EVALS = "App no importa evals"


def test_app_no_importa_evals(tmp_path):
    # evals es tooling hermano de app: evals -> app vale, app -> evals no (la imagen de api no trae evals).
    _arbol_modulos(tmp_path, "app/x.py", "import evals\n")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals/__init__.py").touch()

    r = lint_imports(tmp_path)

    assert r.returncode != 0, r.stdout + r.stderr
    assert f"{SIN_EVALS} BROKEN" in r.stdout


def test_repo_cumple_contratos():
    r = lint_imports(BACKEND)
    assert r.returncode == 0, r.stdout + r.stderr


def test_acceso_dominio_no_importa_su_infraestructura(tmp_path):
    _arbol_modulos(tmp_path, "app/modulos/acceso/dominio/x.py", "import app.modulos.acceso.infraestructura\n")

    r = lint_imports(tmp_path)

    assert r.returncode != 0
    assert f"{CAPAS} BROKEN" in r.stdout


SIN_HTTP_ENRIQ = "Enriquecimiento: dominio sin HTTP ni infraestructura"


def test_enriquecimiento_dominio_no_importa_httpx(tmp_path):
    _arbol_modulos(tmp_path, "app/modulos/enriquecimiento/dominio/x.py", "import httpx\n")

    r = lint_imports(tmp_path)

    assert r.returncode != 0
    assert f"{SIN_HTTP_ENRIQ} BROKEN" in r.stdout
