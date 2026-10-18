"""Esquema y whitelist de los JSON versionados en evals/ (el repo es público).

Dos chequeos:
- problemas_contacto: cada clave en la whitelist de su nivel y ningún valor con forma de email o teléfono.
- problemas_dataset: estructura de dataset.json y las reglas de cumplimiento por caso
  (nombre solo de jurídica de OSM; Croma sin nombre ni NIT, id aleatorio).
Cada problema es "regla:ruta"; la ruta nunca lleva el valor, para no repetir lo que se quiere esconder.
"""
import math
import re
from datetime import datetime
from pathlib import Path

import yaml

FUENTES_YAML = Path(__file__).resolve().parents[1] / "config" / "fuentes.yaml"
OSM = "osm_overpass"


def _fuentes_croma() -> frozenset[str]:
    registro = yaml.safe_load(FUENTES_YAML.read_text())
    return frozenset(k for seccion in ("fuentes_descubrimiento", "enriquecedores")
                     for k in registro[seccion] if k.startswith("croma_"))


FUENTES_CROMA = _fuentes_croma()
FUENTES = FUENTES_CROMA | {OSM}

RANGOS_INGRESOS = ("micro", "pequena", "mediana", "grande")
ETIQUETAS = ("encaja", "no_encaja")
ICP = {"pais", "ciiu", "departamentos", "descripcion"}
EVALS = ("encaje_icp", "juez_mensaje_calibracion")

_CASO = {"id", "pais", "actividad", "departamento", "ciudad", "rango_ingresos",
         "tipo_titular", "nombre", "origen", "etiqueta"}
_BASELINE = {"agregado", "determinacion", "k", "n", "fingerprint", "fecha", "motivo"}

# Por archivo, la whitelist de cada nivel: la ruta de claves (sin índices de listas) → claves permitidas.
WHITELIST: dict[str, dict[tuple[str, ...], set[str]]] = {
    "dataset.json": {
        (): {"icp", "casos"},
        ("icp",): ICP,
        ("casos",): _CASO,
        ("casos", "origen"): {"fuente", "as_of", "licencia"},
    },
    "casos/calibracion_mensajes.json": {
        (): {"id", "lead", "mensaje", "pertinente"},
        ("lead",): {"nombre", "pais", "actividad", "ciudad", "departamento"},
        ("mensaje",): {"asunto", "cuerpo", "adjuntos"},
    },
    "baseline.json": {(): set(EVALS), **{(nombre,): _BASELINE for nombre in EVALS}},
}

EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")  # sin `.` en las etiquetas: sin backtracking (Sonar)
# 7+ dígitos con separadores opcionales; la coma no separa ("4711, 4719" es una lista de CIIU).
TELEFONO = re.compile(r"\d(?:[ .\-()]*\d){6,}")
FECHA_EN_TEXTO = re.compile(r"\d{4}-\d{2}-\d{2}")
ID_ALEATORIO = re.compile(r"[co]-[0-9a-f]{12}")  # c- Croma, o- OSM: secrets.token_hex(6) al exportar
ID_CROMA = re.compile(r"c-[0-9a-f]{12}")
FINGERPRINT = re.compile(r"[0-9a-f]{64}")
NIT = re.compile(r"\d{9}")


def _es_fecha_iso(valor) -> bool:
    # Formato extendido obligatorio: fromisoformat acepta "20261017", que es indistinguible de un número.
    if not isinstance(valor, str) or not FECHA_EN_TEXTO.match(valor):
        return False
    try:
        datetime.fromisoformat(valor)
    except ValueError:
        return False
    return True


def _exento(clave, valor) -> bool:
    if not isinstance(valor, str):
        return False
    return ((clave == "id" and ID_ALEATORIO.fullmatch(valor) is not None)
            or (clave == "fingerprint" and FINGERPRINT.fullmatch(valor) is not None)
            or (clave in ("as_of", "fecha") and _es_fecha_iso(valor)))


def _texto(valor) -> str:
    if isinstance(valor, bool) or valor is None:
        return ""
    if isinstance(valor, (int, float)):
        # Solo la parte entera: 11/15 = 0.7333333333333333 no es un teléfono; 900123456.0 sí.
        return str(abs(int(valor))) if math.isfinite(valor) else ""
    if isinstance(valor, str):
        return FECHA_EN_TEXTO.sub(" ", valor)  # una fecha dentro de un texto no es un teléfono
    return ""


def _ver(valor, clave, nivel, donde, niveles, problemas) -> None:
    if isinstance(valor, dict):
        for k, v in valor.items():
            if k not in niveles.get(nivel, set()):
                problemas.append(f"clave:{donde}.{k}")
            _ver(v, k, nivel + (k,), f"{donde}.{k}", niveles, problemas)
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            _ver(v, clave, nivel, f"{donde}[{i}]", niveles, problemas)
    elif not _exento(clave, valor):
        texto = _texto(valor)
        if EMAIL.search(texto):
            problemas.append(f"email:{donde}")
        if TELEFONO.search(texto):
            problemas.append(f"telefono:{donde}")


def problemas_contacto(archivo: str, datos) -> list[str]:
    niveles = WHITELIST.get(archivo)
    if niveles is None:
        return [f"archivo:{archivo}"]
    problemas: list[str] = []
    _ver(datos, None, (), "$", niveles, problemas)
    return problemas


def _strings(valor, clave=None):
    if isinstance(valor, dict):
        for k, v in valor.items():
            yield from _strings(v, k)
    elif isinstance(valor, list):
        for v in valor:
            yield from _strings(v, clave)
    elif isinstance(valor, str) and clave != "id":
        yield valor


def _problemas_caso(caso: dict, donde: str) -> list[str]:
    problemas = []
    origen = caso.get("origen")
    fuente = origen.get("fuente") if isinstance(origen, dict) else None
    if (fuente not in FUENTES or not _es_fecha_iso(origen.get("as_of"))
            or not isinstance(origen.get("licencia"), str) or not origen["licencia"]):
        problemas.append(f"origen:{donde}")
    if caso.get("etiqueta") not in ETIQUETAS:
        problemas.append(f"etiqueta:{donde}")
    if "nombre" in caso and not (caso.get("tipo_titular") == "juridica" and fuente == OSM):
        problemas.append(f"nombre:{donde}")
    if "rango_ingresos" in caso and caso["rango_ingresos"] not in RANGOS_INGRESOS:
        problemas.append(f"rango_ingresos:{donde}")
    if fuente in FUENTES_CROMA:
        if not (isinstance(caso.get("id"), str) and ID_CROMA.fullmatch(caso["id"])):
            problemas.append(f"croma_id:{donde}")
        if any(NIT.search(s) for s in _strings(caso)):
            problemas.append(f"croma_digitos:{donde}")
    return problemas


def problemas_dataset(datos) -> list[str]:
    if not isinstance(datos, dict):
        return ["raiz:$"]
    problemas = []
    icp = datos.get("icp")
    if not isinstance(icp, dict) or not ICP <= icp.keys():
        problemas.append("icp:$.icp")
    casos = [c for c in datos.get("casos") or [] if isinstance(c, dict)]
    if not 20 <= len(casos) <= 40:
        problemas.append("n_casos:$.casos")
    ids = [c.get("id") for c in casos]
    for i, caso in enumerate(casos):
        donde = f"$.casos[{i}]"
        if ids.count(caso.get("id")) > 1:
            problemas.append(f"id_duplicado:{donde}")
        problemas += _problemas_caso(caso, donde)
    for etiqueta in ETIQUETAS:
        if sum(c.get("etiqueta") == etiqueta for c in casos) < 5:
            problemas.append(f"min_por_etiqueta:{etiqueta}")
    return problemas


def rango_ingresos(cop: int) -> str:
    """Bucket de ingresos anuales en pesos COP (no miles), los que reporta Supersociedades."""
    if cop < 1_000_000_000:
        return "micro"
    if cop < 10_000_000_000:
        return "pequena"
    if cop <= 50_000_000_000:
        return "mediana"
    return "grande"
