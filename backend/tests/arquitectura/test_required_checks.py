"""Configuración del repo (spec 012, principio V): required checks, steps de seguridad y gate de `security`.

Lee los archivos de `.github/` y nunca toca la API de GitHub: la protección de rama real la
compara `verificar_proteccion.sh`, que corre el dueño del repo (el token de Actions no es admin).
"""
import itertools
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

GITHUB = Path(__file__).resolve().parents[3] / ".github"
WORKFLOWS = GITHUB / "workflows"
REQUIRED = GITHUB / "required-checks.txt"
VEREDICTO = GITHUB / "scripts" / "veredicto_security.sh"
# Corre solo en push a main (deploy de migraciones): en un PR nunca reporta, y como required trabaría main.
EXCLUIDOS = {("ci.yml", "migrar")}


def _workflow(nombre: str) -> dict:
    ruta = WORKFLOWS / nombre
    assert ruta.is_file(), f"falta .github/workflows/{nombre}"
    return yaml.safe_load(ruta.read_text())


def _eventos(wf: dict) -> set[str]:
    # PyYAML 1.1 lee la clave `on` como True.
    on = wf.get("on", wf.get(True))
    if isinstance(on, str):
        return {on}
    return set(on)


def _check_runs(job_id: str, job: dict) -> list[str]:
    """Nombres de check-run como los arma GitHub, que es lo que compara la protección de rama.

    Sin matriz: `name:` o el id. Con matriz: si `name:` usa `${{ matrix.x }}` se sustituye;
    si no, GitHub agrega ` (v1, v2)` con los valores de la combinación.
    """
    nombre = job.get("name", job_id)
    matriz = (job.get("strategy") or {}).get("matrix")
    if not matriz:
        return [nombre]
    # ponytail: solo claves con lista literal; sin include/exclude ni fromJSON. Si un workflow los usa, falla acá.
    assert not {"include", "exclude"} & set(matriz), f"{job_id}: include/exclude no soportado por el test"
    claves = list(matriz)
    nombres = []
    for valores in itertools.product(*(matriz[c] for c in claves)):
        combo = dict(zip(claves, map(str, valores)))
        if "${{" in nombre:
            nombres.append(re.sub(r"\$\{\{\s*matrix\.(\w+)\s*\}\}", lambda m: combo[m.group(1)], nombre))
        else:
            nombres.append(f"{nombre} ({', '.join(combo.values())})")
    return nombres


def _requeridos() -> list[str]:
    assert REQUIRED.is_file(), "falta .github/required-checks.txt"
    lineas = (l.strip() for l in REQUIRED.read_text().splitlines())
    return [l for l in lineas if l and not l.startswith("#")]


def _steps(wf: dict):
    for job in wf["jobs"].values():
        yield from job.get("steps", [])


def test_derivacion_de_nombres_como_github():
    # Prueba el helper con casos fijos: si deriva mal, el test de abajo compara contra nombres falsos.
    assert _check_runs("back", {}) == ["back"]
    assert _check_runs("a", {"name": "Analyze"}) == ["Analyze"]
    assert _check_runs("codeql", {"strategy": {"matrix": {"language": ["python", "javascript-typescript"]}}}) == [
        "codeql (python)", "codeql (javascript-typescript)",
    ]
    assert _check_runs("a", {"name": "Analyze (${{ matrix.language }})",
                             "strategy": {"matrix": {"language": ["python"]}}}) == ["Analyze (python)"]
    assert _check_runs("t", {"strategy": {"matrix": {"os": ["linux"], "py": [3.12]}}}) == ["t (linux, 3.12)"]


def test_cada_check_requerido_existe_como_job():
    for archivo, job_id in EXCLUIDOS:
        assert job_id in _workflow(archivo)["jobs"], f"EXCLUIDOS nombra {archivo}:{job_id}, que ya no existe"
    # Solo workflows que corren en PR: un required que nunca reporta en un PR traba el merge.
    derivados = {
        nombre
        for ruta in WORKFLOWS.glob("*.yml")
        if "pull_request" in _eventos(wf := yaml.safe_load(ruta.read_text()))
        for job_id, job in wf["jobs"].items()
        if (ruta.name, job_id) not in EXCLUIDOS
        for nombre in _check_runs(job_id, job)
    }
    requeridos = _requeridos()

    huerfanos = [n for n in requeridos if n not in derivados]
    assert not huerfanos, f"required-checks.txt nombra checks que ningún workflow produce: {huerfanos}"

    faltan = []
    for archivo in ("ci.yml", "codeql.yml"):
        wf = _workflow(archivo)
        if "pull_request" not in _eventos(wf):
            faltan.append(f"{archivo} no corre en pull_request")
            continue
        for job_id, job in wf["jobs"].items():
            if (archivo, job_id) in EXCLUIDOS:
                continue
            faltan += [f"{archivo}:{n}" for n in _check_runs(job_id, job) if n not in requeridos]
    assert not faltan, f"jobs de PR que no están en required-checks.txt: {faltan}"


def _dependabot():
    eco = {u["package-ecosystem"] for u in yaml.safe_load((GITHUB / "dependabot.yml").read_text())["updates"]}
    assert {"uv", "npm", "github-actions", "docker"} <= eco, f"dependabot sin todos los ecosistemas: {eco}"


def _ci_corre(*fragmentos):
    def chequeo():
        runs = [s.get("run", "") for s in _steps(_workflow("ci.yml"))]
        assert any(all(f in r for f in fragmentos) for r in runs), f"ci.yml no tiene un step con {fragmentos}"
    return chequeo


def _codeql_analiza():
    wf = _workflow("codeql.yml")
    assert {"pull_request", "push"} <= _eventos(wf), "codeql.yml tiene que correr en pull_request y push"
    lenguajes = set()
    for job in wf["jobs"].values():
        matriz = (job.get("strategy") or {}).get("matrix") or {}
        for s in job.get("steps", []):
            if s.get("uses", "").startswith("github/codeql-action/init@"):
                pedido = str((s.get("with") or {}).get("languages", ""))
                if re.fullmatch(r"\$\{\{\s*matrix\.language\s*\}\}", pedido):
                    lenguajes |= set(matriz.get("language", []))
                else:
                    lenguajes |= {l.strip() for l in pedido.split(",") if l.strip()}
    assert {"python", "javascript-typescript"} <= lenguajes, f"codeql.yml analiza {lenguajes or 'nada'}"
    # Decisión del dueño: mismos nombres que el default setup, para que los checks no cambien.
    runs = {n for job_id, job in wf["jobs"].items() for n in _check_runs(job_id, job)}
    assert {"Analyze (python)", "Analyze (javascript-typescript)"} <= runs, f"check-runs de codeql.yml: {runs}"


def _codeql_pinneado_por_sha():
    usos = [s["uses"] for s in _steps(_workflow("codeql.yml")) if s.get("uses", "").startswith("github/codeql-action/")]
    assert usos, "codeql.yml no usa github/codeql-action"
    sin_sha = [u for u in usos if not re.fullmatch(r"[^@]+@[0-9a-f]{40}", u)]
    assert not sin_sha, f"github/codeql-action sin pinnear por SHA de commit: {sin_sha}"


# Lo que la spec promete del agente en CI: sin Bash, sin red y sin escritura.
PROHIBIDAS = {"Bash", "Edit", "Write", "WebFetch", "WebSearch"}


def _problemas_revision(job: dict) -> list[str]:
    """Reglas del job revision-seguridad. Cada problema empieza con su clave, para que el test sepa cuál saltó."""
    problemas = []
    cond = " ".join(str(job.get("if", "")).split())
    cond = re.sub(r"^\$\{\{\s*(.*?)\s*\}\}$", r"\1", cond)  # `${{ x }}` y `x` son el mismo if para GitHub
    runs = "\n".join(s.get("run", "") for s in job.get("steps", []))
    permitidas = re.findall(r"--allowedTools[ =]['\"]?([^\s'\"]+)", runs)
    # --allowedTools solo preaprueba: no saca nada. Lo que no se puede usar lo saca --disallowedTools.
    prohibidas = {t for v in re.findall(r"--disallowedTools[ =]['\"]?([^\s'\"]+)", runs) for t in v.split(",")}
    bypass = [b for b in ("dangerously-skip-permissions", "bypassPermissions") if b in runs]
    if cond != "github.event_name == 'pull_request'":
        problemas.append(f"if: tiene que correr solo en PR, es {cond!r}")
    if "veredicto_security.sh" not in runs:
        problemas.append("veredicto: la salida no pasa por veredicto_security.sh")
    if permitidas != ["Read,Grep,Glob"]:
        problemas.append(f"allowed: --allowedTools tiene que ser Read,Grep,Glob: {permitidas}")
    if not PROHIBIDAS <= prohibidas:
        problemas.append(f"disallowed: --disallowedTools sin {sorted(PROHIBIDAS - prohibidas)}")
    if bypass:
        problemas.append(f"bypass: no puede saltear permisos: {bypass}")
    if not re.search(r"@anthropic-ai/claude-code@\d+\.\d+\.\d+(?![\w.-])", runs):
        problemas.append("pin: la CLI de claude no está pinneada a versión exacta")
    return problemas


def _job_revision(si="github.event_name == 'pull_request'", instalar="@anthropic-ai/claude-code@2.1.0",
                  permitidas="--allowedTools Read,Grep,Glob",
                  prohibidas="--disallowedTools Bash,Edit,Write,WebFetch,WebSearch",
                  extra="", veredicto="| .github/scripts/veredicto_security.sh") -> dict:
    return {"if": si, "steps": [
        {"run": f"npm install -g {instalar}"},
        {"run": f'claude -p "$PROMPT" {permitidas} {prohibidas} {extra} {veredicto}'},
    ]}


CASOS_REVISION = {
    "bueno": (_job_revision(), []),
    "if-envuelto-ok": (_job_revision(si="${{ github.event_name == 'pull_request' }}"), []),
    "if-con-push": (_job_revision(si="github.event_name == 'push'"), ["if"]),
    "if-envuelto-con-and": (_job_revision(si="${{ github.event_name == 'pull_request' && true }}"), ["if"]),
    "sin-veredicto": (_job_revision(veredicto="> reporte.md"), ["veredicto"]),
    "allowed-con-bash": (_job_revision(permitidas="--allowedTools Read,Grep,Glob,Bash"), ["allowed"]),
    "sin-disallowed": (_job_revision(prohibidas=""), ["disallowed"]),
    "disallowed-solo-bash": (_job_revision(prohibidas="--disallowedTools Bash"), ["disallowed"]),
    "bypass": (_job_revision(extra="--permission-mode bypassPermissions"), ["bypass"]),
    "cli-latest": (_job_revision(instalar="@anthropic-ai/claude-code@latest"), ["pin"]),
}


@pytest.mark.parametrize("job, esperado", CASOS_REVISION.values(), ids=CASOS_REVISION.keys())
def test_reglas_de_revision_seguridad(job, esperado):
    # Cada caso malo rompe una sola regla: si la regla se borra, su caso falla.
    assert [p.split(":")[0] for p in _problemas_revision(job)] == esperado


def _revision_seguridad():
    job = _workflow("ci.yml")["jobs"].get("revision-seguridad")
    assert job, "ci.yml no tiene el job revision-seguridad"
    problemas = _problemas_revision(job)
    assert not problemas, f"revision-seguridad: {problemas}"


@pytest.mark.parametrize("chequeo", [
    pytest.param(_dependabot, id="dependabot"),
    pytest.param(_ci_corre("pip-audit"), id="pip-audit"),
    pytest.param(_ci_corre("npm audit --audit-level=high"), id="npm-audit"),
    # Repuesto con el PR #19: versión fija, descarga verificada, --redact (spec 012, Gitleaks).
    pytest.param(_ci_corre("sha256sum --check", "gitleaks git", "--redact"), id="gitleaks"),
    pytest.param(_codeql_analiza, id="codeql-lenguajes"),
    pytest.param(_codeql_pinneado_por_sha, id="codeql-pinneado"),
    pytest.param(_revision_seguridad, id="revision-seguridad"),
])
def test_constitucion_v_tiene_su_step(chequeo):
    chequeo()


PASA = 0
FALLA = 1
CASOS_VEREDICTO = {
    "pasa": ("## Revisión de seguridad\nVeredicto: PASA\nLimpio.\n", PASA),
    "pasa-con-observaciones": ("## Revisión de seguridad\nVeredicto: PASA CON OBSERVACIONES\n| LOW | a.py:1 | x | y |\n", PASA),
    "bloquea": ("## Revisión de seguridad\nVeredicto: BLOQUEA\n| HIGH | a.py:1 | x | y |\n", FALLA),
    "sin-linea": ("## Revisión de seguridad\nTodo bien, PASA.\n", FALLA),
    "vacia": ("", FALLA),
    "en-bloque-de-codigo": ("Ejemplo:\n```\nVeredicto: PASA\n```\nVeredicto pendiente.\n", FALLA),
    # El bloque de código no cuenta, tampoco para bloquear: vale la única línea de afuera.
    "bloque-de-codigo-y-pasa-afuera": ("```\nVeredicto: BLOQUEA\n```\nVeredicto: PASA\n", PASA),
    # 4 espacios de sangría = bloque de código en markdown.
    "sangria-de-4-espacios": ("    Veredicto: PASA\n", FALLA),
    "linea-no-exacta": ("Veredicto: PASA | BLOQUEA\n", FALLA),
    "dos-lineas": ("Veredicto: BLOQUEA\nVeredicto: PASA\n", FALLA),
    # La plantilla de .claude/agents/security.md copiada sin elegir.
    "plantilla-sin-completar": ("Veredicto: BLOQUEA / Veredicto: PASA CON OBSERVACIONES / Veredicto: PASA\n", FALLA),
}


@pytest.mark.parametrize("reporte, esperado", CASOS_VEREDICTO.values(), ids=CASOS_VEREDICTO.keys())
def test_revision_seguridad_es_fail_closed(reporte, esperado):
    # Sin estos asserts, un script ausente o sin +x da error (no veredicto) y los casos FALLA nacerían verdes.
    assert VEREDICTO.is_file(), "falta .github/scripts/veredicto_security.sh"
    assert os.access(VEREDICTO, os.X_OK), "veredicto_security.sh sin permiso de ejecución: CI lo invoca directo"
    # Directo, sin `bash`, como CI invoca check_imagen.sh: el shebang y el +x también se prueban.
    r = subprocess.run([str(VEREDICTO)], input=reporte, capture_output=True, text=True)
    if esperado == PASA:
        assert r.returncode == 0, f"tenía que pasar y salió {r.returncode}: {r.stdout}{r.stderr}"
    else:
        assert r.returncode != 0, "tenía que bloquear y salió 0"
