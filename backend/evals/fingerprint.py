"""Fingerprint de un eval: cambia si cambia lo que define su resultado. Sin `k` ni `tolerancia`."""
import hashlib
import json


def fingerprint(casos: bytes, prompt: bytes, modelo: str, corte: float, umbral: float) -> str:
    canonico = json.dumps({"casos": casos.decode("utf-8"), "prompt": prompt.decode("utf-8"),
                           "modelo": modelo, "corte": corte, "umbral": umbral}, sort_keys=True)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()
