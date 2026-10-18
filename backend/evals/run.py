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
from decimal import Decimal
from pathlib import Path

import httpx
import yaml

from evals.config import ConfigInvalida, cargar
from evals.fingerprint import fingerprint
from evals.jueces.puerto import ErrorJuez, SalidaJuezInvalida
from evals.scorers import forma

CONFIG_DEFAULT = Path(__file__).parent / "evals.yaml"
TARIFAS = Path(__file__).parents[1] / "config" / "tarifas.yaml"
API_ANTHROPIC = "https://api.anthropic.com"
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


def _tarifas_llm() -> dict[str, dict[str, Decimal]]:
    # Decimal(str(v)), nunca Decimal(v): el float 0.10 arrastra 0.1000000000000000055… al costo_unitario.
    llm = yaml.safe_load(TARIFAS.read_text())["llm"]
    return {modelo: {k: Decimal(str(v)) for k, v in t.items()} for modelo, t in llm.items()}


def componer(entorno, transporte=None, *, tenant, evals, carpeta, registro_costos=None):
    """Rama por defecto: JuezClaude del CATALOGO + PostgresCostos del 002 (o el registro inyectado).

    `transporte` es la costura de los tests (httpx.MockTransport); en producción, None = red real.
    La key sale del mapeo `entorno`, nunca del entorno del proceso. Lanza ConfigInvalida antes de cualquier request.
    """
    from evals.jueces.catalogo import CATALOGO
    from evals.jueces.claude import JuezClaude

    try:
        tenant_id = uuid.UUID(tenant)
    except ValueError as e:
        raise ConfigInvalida("--tenant no es un uuid") from e
    tarifas = _tarifas_llm()
    for nombre, ev in evals.items():
        if CATALOGO.get(ev["juez"]) is not JuezClaude:
            raise ConfigInvalida(f"{nombre}: juez {ev['juez']} no se compone desde evals.yaml")
        if ev["modelo"] not in tarifas:
            raise ConfigInvalida(f"{nombre}: sin tarifa llm para {ev['modelo']}")
    if registro_costos is None:
        from app.db import crear_engine
        from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
        registro_costos = PostgresCostos(crear_engine(entorno["DATABASE_URL"]), tenant_id)
    # ponytail: un cliente por corrida que no se cierra; vive lo que vive el proceso del CLI.
    http = httpx.Client(base_url=API_ANTHROPIC, transport=transporte, timeout=60)

    def fabrica(nombre, lote_id):
        ev = evals[nombre]
        return JuezClaude(registro_costos=registro_costos, tarifa=tarifas[ev["modelo"]], modelo=ev["modelo"],
                          prompt=(carpeta / ev["prompt"]).read_text(encoding="utf-8"), lote_id=lote_id,
                          api_key=entorno["ANTHROPIC_API_KEY"], http_client=http)
    return fabrica


def main(argv, entorno=os.environ, fabrica_juez=None, registro_costos=None, transporte=None) -> int:
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
        try:
            fabrica_juez = componer(entorno, transporte, tenant=args.tenant, evals=evals, carpeta=args.config.parent,
                                    registro_costos=registro_costos)
        except ConfigInvalida as e:
            return _error(f"config_invalida: {e}")

    lote_id = uuid.uuid4()
    jueces = {}
    for nombre, ev in evals.items():
        jueces[nombre] = fabrica_juez(nombre, lote_id)
        if not _k_valido(ev, jueces[nombre], baseline.get(nombre)):
            return _error(f"config_invalida: {nombre}: k={ev['k']} sin determinación demostrada a k=3")

    try:
        resultados = {nombre: _correr(nombre, ev, jueces[nombre]) for nombre, ev in evals.items()}
    except ErrorJuez as e:
        return _error(f"juez_error: {e}")  # la API no respondió: no se pudo evaluar (2), no es regresión (1)
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


# El job `evals` del CI corre este módulo sin ANTHROPIC_API_KEY ni --tenant y espera 0. La composición real
# ya existe (componer), pero conectar acá `main(sys.argv[1:])` haría salir 2 ese job: pendiente de decisión
# del dueño (cambiar el job o este __main__). Mientras tanto no llama a main.
if __name__ == "__main__":
    raise SystemExit(0)
