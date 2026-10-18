"""Runner de evals: `uv run python -m evals.run --tenant <id> [--eval <nombre>] [--actualizar-baseline]`.

Códigos: 0 ok; 1 regresión, bajo umbral, sin baseline o baseline obsoleto; 2 falta entorno o config inválida.
El reporte va en JSON por stdout; los errores, como código por stderr. Ningún valor del entorno se imprime.
"""
import argparse
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

from evals.config import ConfigInvalida, cargar
from evals.fingerprint import fingerprint
from evals.jueces.puerto import SalidaJuezInvalida
from evals.scorers import forma

CONFIG_DEFAULT = Path(__file__).parent / "evals.yaml"
ENTORNO_REQUERIDO = ("ANTHROPIC_API_KEY", "DATABASE_URL")


def _r(x: float) -> float:
    # Comparaciones con baseline redondeadas: el error de float no cambia un "ok" por "regresion".
    return round(x, 9)


# Cada eval de la spec trae su forma de dataset. Un caso preparado: (id, lo que ve el juez, etiqueta positiva, regla de forma que falla).
def _casos_encaje(datos) -> list[tuple]:
    if not isinstance(datos, dict) or "icp" not in datos or not isinstance(datos.get("casos"), list):
        raise ConfigInvalida("encaje_icp: el dataset es {icp, casos}")
    casos = []
    for c in datos["casos"]:
        if not isinstance(c, dict) or "id" not in c or c.get("etiqueta") not in ("encaja", "no_encaja"):
            raise ConfigInvalida("encaje_icp: caso sin id o con etiqueta ausente o inválida")
        para_juez = {k: v for k, v in c.items() if k != "etiqueta"} | {"icp": datos["icp"]}
        casos.append((c["id"], para_juez, c["etiqueta"] == "encaja", None))
    return casos


def _casos_calibracion(datos) -> list[tuple]:
    if not isinstance(datos, list):
        raise ConfigInvalida("juez_mensaje_calibracion: el dataset es una lista de mensajes")
    casos = []
    for m in datos:
        if not isinstance(m, dict) or "id" not in m or not isinstance(m.get("mensaje"), dict) \
                or not isinstance(m.get("pertinente"), bool):
            raise ConfigInvalida("juez_mensaje_calibracion: mensaje sin id, sin mensaje o con pertinente inválido")
        para_juez = {k: v for k, v in m.items() if k != "pertinente"}
        casos.append((m["id"], para_juez, m["pertinente"], forma.mensaje(m["mensaje"])))
    return casos


# ponytail: el tipo de eval se elige por su nombre en evals.yaml (un eval por tipo). Si aparece un
# segundo eval del mismo tipo, agregar un campo `tipo:` en evals.yaml y despachar por ese campo.
PREPARAR = {"encaje_icp": _casos_encaje, "juez_mensaje_calibracion": _casos_calibracion}


def _args(argv):
    p = argparse.ArgumentParser(prog="evals.run")
    p.add_argument("--config", type=Path, default=CONFIG_DEFAULT)
    p.add_argument("--tenant")
    p.add_argument("--eval")
    p.add_argument("--actualizar-baseline", action="store_true")
    p.add_argument("--motivo")
    return p.parse_args(argv)


def _preparar(args) -> tuple[dict[str, dict], dict]:
    evals = cargar(args.config)
    if args.eval is not None:
        if args.eval not in evals:
            raise ConfigInvalida(f"--eval {args.eval}: no está en evals.yaml")
        evals = {args.eval: evals[args.eval]}
    carpeta = args.config.parent
    for nombre, ev in evals.items():
        if nombre not in PREPARAR:  # ponytail: despacho por nombre, ver PREPARAR
            raise ConfigInvalida(f"{nombre}: eval desconocido")
        if args.actualizar_baseline and ev["k"] < 3:
            raise ConfigInvalida(f"{nombre}: el baseline solo se fija a k=3")
        try:
            casos, prompt = (carpeta / ev["casos"]).read_bytes(), (carpeta / ev["prompt"]).read_bytes()
            ev["casos_preparados"] = PREPARAR[nombre](json.loads(casos))
            ev["fingerprint"] = fingerprint(casos, prompt, ev["modelo"], ev["corte"], ev["umbral"])
        except (OSError, ValueError) as e:  # UnicodeDecodeError y JSONDecodeError son ValueError
            raise ConfigInvalida(f"{nombre}: casos o prompt ilegibles ({type(e).__name__})") from e
        if not ev["casos_preparados"]:
            raise ConfigInvalida(f"{nombre}: sin casos")
    ruta = carpeta / "baseline.json"
    try:
        baseline = json.loads(ruta.read_text()) if ruta.exists() else {}
    except ValueError as e:
        raise ConfigInvalida("baseline.json ilegible") from e
    return evals, baseline


def _k_valido(ev: dict, juez, b: dict | None) -> bool:
    # k < 3 solo con un juez que puede demostrar determinación y un baseline vigente a k=3 con determinacion 1.0.
    return ev["k"] >= 3 or bool(juez.determinista_si_se_demuestra and b and b.get("fingerprint") == ev["fingerprint"]
                                and b.get("k") == 3 and b.get("determinacion") == 1.0)


def _correr(nombre: str, ev: dict, juez) -> dict:
    pasan = juzgados = deterministas = 0
    fallidos = []
    for id_, caso, positivo, regla in ev["casos_preparados"]:
        if regla:  # forma primero: si falla, no se gasta el juez
            fallidos.append({"id": id_, "motivo": f"forma:{regla}"})
            continue
        resultados, invalida = [], False
        for _ in range(ev["k"]):  # un caso por llamada
            try:
                resultados.append((juez.juzgar(nombre, caso).probabilidad >= ev["corte"]) == positivo)
            except SalidaJuezInvalida:
                resultados.append(False)
                invalida = True
        juzgados += 1
        deterministas += len(set(resultados)) == 1
        if all(resultados):
            pasan += 1
        else:
            fallidos.append({"id": id_, "motivo": "juez_salida_invalida" if invalida else "fallo_corrida"})
    return {"agregado": pasan / len(ev["casos_preparados"]),
            "determinacion": deterministas / juzgados if juzgados else None,
            "k": ev["k"], "n": len(ev["casos_preparados"]), "fingerprint": ev["fingerprint"],
            "umbral": ev["umbral"], "fallidos": fallidos}


def _estado(r: dict, ev: dict, b: dict | None) -> str:
    if _r(r["agregado"]) < _r(ev["umbral"]):
        return "bajo_umbral"
    if b is None:
        return "sin_baseline"
    if b.get("fingerprint") != r["fingerprint"]:
        return "baseline_obsoleto"
    if _r(r["agregado"]) < _r(b["agregado"] - ev["tolerancia"]):
        return "regresion"
    return "ok"


def _compara(r: dict, b: dict | None, cmp) -> bool:
    """¿agregado o determinacion cumplen `cmp(corrida, baseline)` contra un baseline vigente del mismo fingerprint?"""
    if not b or b.get("fingerprint") != r["fingerprint"]:
        return False
    pares = [(r["agregado"], b.get("agregado")), (r["determinacion"], b.get("determinacion"))]
    return any(x is not None and y is not None and cmp(_r(x), _r(y)) for x, y in pares)


def _error(codigo: str) -> int:
    print(codigo, file=sys.stderr)
    return 2


def main(argv, entorno=os.environ, fabrica_juez=None, registro_costos=None) -> int:
    try:
        args = _args(argv)
    except SystemExit:
        return 2
    if faltan := [v for v in ENTORNO_REQUERIDO if not entorno.get(v)] + ([] if args.tenant else ["--tenant"]):
        return _error(f"falta_entorno: {', '.join(faltan)}")  # nombres, nunca valores
    try:
        evals, baseline = _preparar(args)
    except ConfigInvalida as e:
        return _error(f"config_invalida: {e}")
    if fabrica_juez is None:
        raise NotImplementedError("composición real (JuezClaude + postgres_costos): T019")

    lote_id = uuid.uuid4()
    jueces = {}
    for nombre, ev in evals.items():
        jueces[nombre] = fabrica_juez(nombre, lote_id)
        if not _k_valido(ev, jueces[nombre], baseline.get(nombre)):
            return _error(f"config_invalida: {nombre}: k={ev['k']} sin determinación demostrada a k=3")

    resultados = {nombre: _correr(nombre, ev, jueces[nombre]) for nombre, ev in evals.items()}
    for nombre, r in resultados.items():
        r["estado"] = _estado(r, evals[nombre], baseline.get(nombre))
        r["baseline"] = (baseline.get(nombre) or {}).get("agregado")

    mejora_sin_fijar = []
    if args.actualizar_baseline:
        # Bajar el baseline vigente (agregado o determinacion, sin tolerancia) exige --motivo.
        bajan = [n for n, r in resultados.items() if _compara(r, baseline.get(n), lambda x, y: x < y)]
        bloqueado = any(r["estado"] == "bajo_umbral" for r in resultados.values()) or (bajan and not args.motivo)
        if bloqueado:
            for n in bajan:
                if resultados[n]["estado"] == "ok":
                    resultados[n]["estado"] = "regresion"
        else:
            hoy = date.today().isoformat()
            for n, r in resultados.items():
                baseline[n] = {"agregado": r["agregado"], "determinacion": r["determinacion"], "k": r["k"],
                               "n": r["n"], "fingerprint": r["fingerprint"], "fecha": hoy, "motivo": args.motivo}
                r["estado"], r["baseline"] = "ok", r["agregado"]
            (args.config.parent / "baseline.json").write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n")
    else:
        # Mejora = algo sube y nada baja.
        mejora_sin_fijar = [n for n, r in resultados.items()
                            if r["estado"] == "ok" and _compara(r, baseline.get(n), lambda x, y: x > y)
                            and not _compara(r, baseline.get(n), lambda x, y: x < y)]

    print(json.dumps({"lote_id": str(lote_id), "evals": resultados, "mejora_sin_fijar": mejora_sin_fijar}, ensure_ascii=False))
    return 0 if all(r["estado"] == "ok" for r in resultados.values()) else 1


# El CI corre este módulo y espera 0: hasta la composición real (T019) no llama a main.
if __name__ == "__main__":
    raise SystemExit(0)
