"""Configuración del repo (spec 012, principio V): required checks, steps de seguridad y gate de `security`.

Lee los archivos de `.github/` y nunca toca la API de GitHub: la protección de rama real la
compara `verificar_proteccion.sh`, que corre el dueño del repo (el token de Actions no es admin).
"""
import itertools
import json
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
# CodeQL corre por el default setup del repo, no por un workflow propio (GitHub rechaza el SARIF de los dos).
# Nombres vistos en los check-runs del workflow "CodeQL" del PR #23. Analyze (actions) también sale, no es required.
DEFAULT_SETUP = {"Analyze (python)", "Analyze (javascript-typescript)"}


def _workflow(nombre: str) -> dict:
    ruta = WORKFLOWS / nombre
    assert ruta.is_file(), f"falta .github/workflows/{nombre}"
    return yaml.safe_load(ruta.read_text())


def _workflows() -> list[Path]:
    # GitHub corre los .yml y los .yaml de .github/workflows/.
    return sorted(p for p in WORKFLOWS.iterdir() if p.suffix in {".yml", ".yaml"})


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
        for ruta in _workflows()
        if "pull_request" in _eventos(wf := yaml.safe_load(ruta.read_text()))
        for job_id, job in wf["jobs"].items()
        if (ruta.name, job_id) not in EXCLUIDOS
        for nombre in _check_runs(job_id, job)
    }
    requeridos = _requeridos()

    huerfanos = [n for n in requeridos if n not in derivados | DEFAULT_SETUP]
    assert not huerfanos, f"required-checks.txt nombra checks que ningún workflow produce: {huerfanos}"

    faltan = []
    for archivo in ("ci.yml",):
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


# Sin codeql.yml: lo reemplaza el default setup y su workflow no vive en el repo.
FIJADOS = ("ci.yml",)
# e2e.yml choca con el criterio de la 014, que no está en main: specs/012-seguridad/spec.md:168, "e2e.yml sin fijar".
SIN_FIJAR_TODAVIA = {"e2e.yml"}


def _ci_acciones_pinneadas():
    # Explícito: un workflow nuevo no queda afuera en silencio.
    todos = {w.name for w in _workflows()}
    assert todos == set(FIJADOS) | SIN_FIJAR_TODAVIA, f"workflows sin clasificar: {sorted(todos - set(FIJADOS) - SIN_FIJAR_TODAVIA)}"
    sin_sha = []
    for nombre in FIJADOS:
        for n, linea in enumerate((WORKFLOWS / nombre).read_text().splitlines(), 1):
            # Sobre el texto: el `# vX.Y.Z` es un comentario y yaml lo descarta.
            m = re.search(r"uses:\s*['\"]?([^\s'\"]+)['\"]?(.*)", linea)
            if not m or m[1].startswith("./"):
                continue
            if not (re.fullmatch(r"[^@]+@[0-9a-f]{40}", m[1]) and re.fullmatch(r"\s*#\s*v\d+\.\d+\.\d+\s*", m[2])):
                sin_sha.append(f"{nombre}:{n} {m[1]}")
    assert not sin_sha, f"uses: sin SHA de commit con `# vX.Y.Z` al lado: {sin_sha}"


def _ci_checkout_sin_credenciales():
    con = []
    for nombre in FIJADOS:
        checkouts = [s for s in _steps(_workflow(nombre)) if s.get("uses", "").startswith("actions/checkout@")]
        assert checkouts, f"{nombre} no usa actions/checkout"
        # yaml lee `false` como bool: el string "false" no cuenta.
        con += [nombre for s in checkouts if (s.get("with") or {}).get("persist-credentials") is not False]
    assert not con, f"checkout sin persist-credentials: false en {con}"


# Lo que la spec promete del agente en CI: sin Bash, sin red y sin escritura.
# Segunda capa contra la fuga del secret (la primera es el deny de /proc): este corte borra el reporte y
# falla si trae el secret, antes de que llegue al summary o al artifact.
CORTE = re.compile(r'grep -qF "\$ANTHROPIC_API_KEY" revision\.json && \{ rm -f revision\.\*;[^}]*exit 1; \}')
# Read(//proc/**) es la primera capa: sin leer /proc/self/environ el agente no ve el secret. El grep es la segunda.
PROHIBIDAS = {"Bash", "Edit", "Write", "WebFetch", "WebSearch", "Read(//proc/**)"}


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
    # Flags verificados en `claude --help` de la versión pinneada.
    if not re.search(r"--restricted(?![\w-])", runs):
        problemas.append("restricted: falta --restricted (ignora settings del repo y confina las tools de archivo)")
    if not re.search(r"--strict-mcp-config(?![\w-])", runs):
        problemas.append("mcp: falta --strict-mcp-config (sin MCP fuera de --mcp-config)")
    if not re.search(r"@anthropic-ai/claude-code@\d+\.\d+\.\d+(?![\w.-])", runs):
        problemas.append("pin: la CLI de claude no está pinneada a versión exacta")
    if fuga := _fuga_del_secret(job.get("steps", [])):
        problemas.append(f"fuga: {fuga}")
    return problemas


def _fuga_del_secret(steps: list[dict]) -> str:
    """Qué saca el reporte del job antes del corte por `grep -qF` del secret ("" si nada)."""
    corte = next(((i, m.start()) for i, s in enumerate(steps) if (m := CORTE.search(s.get("run", "")))), None)
    if corte is None:
        return "falta el corte por grep -qF del secret en revision.json"
    i_corte, pos = corte
    for i, s in enumerate(steps[:i_corte + 1]):
        run = s.get("run", "")[:pos] if i == i_corte else s.get("run", "")
        if "GITHUB_STEP_SUMMARY" in run:
            return "escribe GITHUB_STEP_SUMMARY antes del corte"
        if "upload-artifact" in s.get("uses", ""):
            return "sube el artifact antes del corte"
    return ""


def _job_revision(si="github.event_name == 'pull_request'", instalar="@anthropic-ai/claude-code@2.1.0",
                  permitidas="--allowedTools Read,Grep,Glob",
                  prohibidas='--disallowedTools "Bash,Edit,Write,WebFetch,WebSearch,Read(//proc/**)"',
                  extra="", modo="--restricted --strict-mcp-config",
                  veredicto="| .github/scripts/veredicto_security.sh",
                  despues=None, artifact_primero=False) -> dict:
    despues = (CORTE_OK, RESUMEN) if despues is None else despues
    artifact = [{"uses": "actions/upload-artifact@v7", "if": "always()"}]
    return {"if": si, "steps": [
        {"run": f"npm install -g {instalar}"},
        *(artifact if artifact_primero else []),
        {"run": "\n".join([f'claude -p "$PROMPT" {modo} {permitidas} {prohibidas} {extra} {veredicto}', *despues])},
        *([] if artifact_primero else artifact),
    ]}


CORTE_OK = 'grep -qF "$ANTHROPIC_API_KEY" revision.json && { rm -f revision.*; echo "BLOQUEA" >&2; exit 1; }'
RESUMEN = 'cat revision.md >> "$GITHUB_STEP_SUMMARY"'


CASOS_REVISION = {
    "bueno": (_job_revision(), []),
    "if-envuelto-ok": (_job_revision(si="${{ github.event_name == 'pull_request' }}"), []),
    "if-con-push": (_job_revision(si="github.event_name == 'push'"), ["if"]),
    "if-envuelto-con-and": (_job_revision(si="${{ github.event_name == 'pull_request' && true }}"), ["if"]),
    "sin-veredicto": (_job_revision(veredicto="> reporte.md"), ["veredicto"]),
    "allowed-con-bash": (_job_revision(permitidas="--allowedTools Read,Grep,Glob,Bash"), ["allowed"]),
    "sin-disallowed": (_job_revision(prohibidas=""), ["disallowed"]),
    "disallowed-solo-bash": (_job_revision(prohibidas="--disallowedTools Bash"), ["disallowed"]),
    "disallowed-sin-proc": (_job_revision(prohibidas="--disallowedTools Bash,Edit,Write,WebFetch,WebSearch"),
                            ["disallowed"]),
    "bypass": (_job_revision(extra="--permission-mode bypassPermissions"), ["bypass"]),
    "sin-restricted": (_job_revision(modo="--strict-mcp-config"), ["restricted"]),
    "sin-strict-mcp": (_job_revision(modo="--restricted"), ["mcp"]),
    "cli-latest": (_job_revision(instalar="@anthropic-ai/claude-code@latest"), ["pin"]),
    "sin-corte": (_job_revision(despues=(RESUMEN,)), ["fuga"]),
    "corte-sin-exit": (_job_revision(despues=(CORTE_OK.replace(" exit 1;", ""), RESUMEN)), ["fuga"]),
    "summary-antes-del-corte": (_job_revision(despues=(RESUMEN, CORTE_OK)), ["fuga"]),
    "artifact-antes-del-corte": (_job_revision(artifact_primero=True), ["fuga"]),
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
    pytest.param(_revision_seguridad, id="revision-seguridad"),
    pytest.param(_ci_acciones_pinneadas, id="ci-acciones-pinneadas"),
    pytest.param(_ci_checkout_sin_credenciales, id="ci-checkout-sin-credenciales"),
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


VERIFICAR = GITHUB / "scripts" / "verificar_proteccion.sh"
# `gh` falso: `gh api <ruta>` devuelve el fixture de esa ruta, o sale 1 como un 404. Sin red ni token.
GH_FALSO = """#!/usr/bin/env bash
[ "$1" = api ] || exit 2
f="$GH_FIXTURES/$(printf %s "$2" | tr / _)"
[ -f "$f" ] || { echo "gh: Not Found (HTTP 404)" >&2; exit 1; }
cat "$f"
"""
PROTECCION = "repos/o/r/branches/main/protection"
REPO = "repos/o/r"
API_DEFAULT_SETUP = "repos/o/r/code-scanning/default-setup"


def _api(**cambios) -> dict:
    api = {
        PROTECCION: {"required_status_checks": {"contexts": _requeridos()}},
        REPO: {"security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
        }},
        API_DEFAULT_SETUP: {"state": "configured"},
    }
    if "contexts" in cambios:
        api[PROTECCION]["required_status_checks"]["contexts"] = cambios["contexts"]
    if "sin_proteccion" in cambios:
        api[PROTECCION] = None
    for clave in ("secret_scanning", "secret_scanning_push_protection"):
        if clave in cambios:
            api[REPO]["security_and_analysis"][clave]["status"] = cambios[clave]
    if "default_setup" in cambios:
        api[API_DEFAULT_SETUP]["state"] = cambios["default_setup"]
    return api


CASOS_PROTECCION = {
    "ok": (lambda: _api(), None),
    # La frase entera, no solo el nombre: con `comm -23` y `comm -13` invertidos, `back` sale como "sobra".
    "falta-un-check": (lambda: _api(contexts=_requeridos()[1:]),
                       lambda: [f"falta el required check: {_requeridos()[0]}"]),
    "sobra-un-check": (lambda: _api(contexts=[*_requeridos(), "Vercel"]),
                       lambda: ["sobra el required check (no está en required-checks.txt): Vercel"]),
    "sin-proteccion": (lambda: _api(sin_proteccion=True), lambda: ["branches/main/protection: no se pudo leer"]),
    "secret-scanning-apagado": (lambda: _api(secret_scanning="disabled"), lambda: ["secret_scanning: disabled"]),
    "push-protection-apagado": (lambda: _api(secret_scanning_push_protection="disabled"),
                                lambda: ["secret_scanning_push_protection: disabled"]),
    # Los Analyze required los publica el default setup: apagado, main queda trabado.
    "default-setup-apagado": (lambda: _api(default_setup="not-configured"),
                              lambda: ["code-scanning/default-setup: not-configured"]),
    # Reporta cada motivo, no solo el primero.
    "dos-fallas": (lambda: _api(contexts=_requeridos()[1:], default_setup="not-configured"),
                   lambda: [f"falta el required check: {_requeridos()[0]}", "code-scanning/default-setup: not-configured"]),
}


@pytest.mark.parametrize("api, motivo", CASOS_PROTECCION.values(), ids=CASOS_PROTECCION.keys())
def test_verificar_proteccion(api, motivo, tmp_path):
    # Perezosos: _requeridos() asserta el archivo, y en la colección rompería todo el módulo.
    api, motivo = api(), motivo and motivo()
    assert VERIFICAR.is_file(), "falta .github/scripts/verificar_proteccion.sh"
    assert os.access(VERIFICAR, os.X_OK), "verificar_proteccion.sh sin permiso de ejecución"
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "gh").write_text(GH_FALSO)
    (bin_ / "gh").chmod(0o755)
    fixtures = tmp_path / "api"
    fixtures.mkdir()
    for ruta, cuerpo in api.items():
        if cuerpo is not None:
            (fixtures / ruta.replace("/", "_")).write_text(json.dumps(cuerpo))
    env = {**os.environ, "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}", "GH_FIXTURES": str(fixtures)}
    r = subprocess.run([str(VERIFICAR), "o/r"], capture_output=True, text=True, env=env)
    salida = r.stdout + r.stderr
    if motivo is None:
        assert r.returncode == 0, f"tenía que pasar y salió {r.returncode}: {salida}"
    else:
        assert r.returncode != 0, f"tenía que fallar por {motivo!r} y salió 0: {salida}"
        # Que falle por esto y no por otra cosa: la salida se pega en docs/seguridad.
        faltan = [m for m in motivo if m not in salida]
        assert not faltan, f"falló sin nombrar {faltan!r}: {salida}"
