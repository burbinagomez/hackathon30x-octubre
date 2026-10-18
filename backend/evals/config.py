"""Carga y valida `evals.yaml`: un mapa `nombre_eval → config`, nada por posición."""
from pathlib import Path

import yaml

DEFAULTS = {"k": 3, "corte": 0.5, "tolerancia": 0}
REQUERIDAS = ("juez", "modelo", "prompt", "casos", "umbral")


class ConfigInvalida(Exception):
    """`evals.yaml`, un dataset o la regla de k no se pueden usar: el runner sale 2."""


def _numero(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def cargar(ruta: Path) -> dict[str, dict]:
    try:
        datos = yaml.safe_load(ruta.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise ConfigInvalida(f"evals.yaml ilegible ({type(e).__name__})") from e
    if not isinstance(datos, dict) or not datos:
        raise ConfigInvalida("evals.yaml tiene que ser un mapa nombre → config")
    evals = {}
    for nombre, cfg in datos.items():
        if not isinstance(cfg, dict):
            raise ConfigInvalida(f"{nombre}: la config tiene que ser un mapa")
        if faltan := [c for c in REQUERIDAS if c not in cfg]:
            raise ConfigInvalida(f"{nombre}: faltan {faltan}")
        cfg = {**DEFAULTS, **cfg}
        if not isinstance(cfg["k"], int) or isinstance(cfg["k"], bool) or cfg["k"] < 1:
            raise ConfigInvalida(f"{nombre}: k tiene que ser un entero ≥ 1")
        if not all(_numero(cfg[c]) for c in ("corte", "umbral", "tolerancia")):
            raise ConfigInvalida(f"{nombre}: corte, umbral y tolerancia son números")
        evals[nombre] = cfg
    return evals
