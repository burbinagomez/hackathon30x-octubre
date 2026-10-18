"""Genera config/geografia/co.yaml. NO corre en runtime ni en CI: se corre a mano y el YAML se versiona.

    python scripts/geografia_co.py                 # baja DIVIPOLA de datos.gov.co (Socrata) y escribe el YAML
    python scripts/geografia_co.py --sin-municipios  # solo los 33 departamentos (sin red)

Los departamentos (código DIVIPOLA, código ISO 3166-2:CO y nombres) están en la tabla de abajo, que es de DANE/ISO;
los municipios salen únicamente del dataset oficial: lo que no esté en él no se inventa.
"""
import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import httpx
import yaml

# DIVIPOLA, dataset de municipios en datos.gov.co. [VALIDAR con red] el id y los campos cod_dpto, cod_mpio, nom_mpio.
DATASET = "gdxc-w37w"
URL = "https://www.datos.gov.co/resource/{dataset}.json"
SALIDA = Path(__file__).resolve().parents[1] / "config" / "geografia" / "co.yaml"

# (código DIVIPOLA, código ISO 3166-2:CO, nombre_es, nombre_en). DANE (DIVIPOLA) e ISO 3166-2:CO.
DEPARTAMENTOS: list[tuple[str, str, str, str]] = [
    ("05", "CO-ANT", "Antioquia", "Antioquia"),
    ("08", "CO-ATL", "Atlántico", "Atlántico"),
    ("11", "CO-DC", "Bogotá, D.C.", "Bogotá, D.C."),
    ("13", "CO-BOL", "Bolívar", "Bolívar"),
    ("15", "CO-BOY", "Boyacá", "Boyacá"),
    ("17", "CO-CAL", "Caldas", "Caldas"),
    ("18", "CO-CAQ", "Caquetá", "Caquetá"),
    ("19", "CO-CAU", "Cauca", "Cauca"),
    ("20", "CO-CES", "Cesar", "Cesar"),
    ("23", "CO-COR", "Córdoba", "Córdoba"),
    ("25", "CO-CUN", "Cundinamarca", "Cundinamarca"),
    ("27", "CO-CHO", "Chocó", "Chocó"),
    ("41", "CO-HUI", "Huila", "Huila"),
    ("44", "CO-LAG", "La Guajira", "La Guajira"),
    ("47", "CO-MAG", "Magdalena", "Magdalena"),
    ("50", "CO-MET", "Meta", "Meta"),
    ("52", "CO-NAR", "Nariño", "Nariño"),
    ("54", "CO-NSA", "Norte de Santander", "Norte de Santander"),
    ("63", "CO-QUI", "Quindío", "Quindío"),
    ("66", "CO-RIS", "Risaralda", "Risaralda"),
    ("68", "CO-SAN", "Santander", "Santander"),
    ("70", "CO-SUC", "Sucre", "Sucre"),
    ("73", "CO-TOL", "Tolima", "Tolima"),
    ("76", "CO-VAC", "Valle del Cauca", "Valle del Cauca"),
    ("81", "CO-ARA", "Arauca", "Arauca"),
    ("85", "CO-CAS", "Casanare", "Casanare"),
    ("86", "CO-PUT", "Putumayo", "Putumayo"),
    ("88", "CO-SAP", "San Andrés y Providencia", "San Andrés and Providencia"),
    ("91", "CO-AMA", "Amazonas", "Amazonas"),
    ("94", "CO-GUA", "Guainía", "Guainía"),
    ("95", "CO-GUV", "Guaviare", "Guaviare"),
    ("97", "CO-VAU", "Vaupés", "Vaupés"),
    ("99", "CO-VID", "Vichada", "Vichada"),
]


class _Codigo(str):
    """Un código (DIVIPOLA, ISO): siempre entre comillas. PyYAML deja '08' sin ellas y un parser YAML 1.2 lo leería como número."""


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(_Codigo, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", str(v), style='"'))
_MINUSCULAS = {"de", "del", "la", "las", "los", "y", "e", "el"}


def _titulo(nombre: str) -> str:
    """'LA JAGUA DE IBIRICO' -> 'La Jagua de Ibirico'; 'BOGOTÁ, D.C.' -> 'Bogotá, D.C.'. El dataset viene en mayúsculas."""
    palabras = []
    for i, palabra in enumerate(nombre.strip().split()):
        if "." in palabra:
            palabras.append(palabra.upper())
        elif i > 0 and palabra.lower() in _MINUSCULAS:
            palabras.append(palabra.lower())
        else:
            palabras.append(palabra[:1].upper() + palabra[1:].lower())
    return " ".join(palabras)


def construir(filas: list[dict], fecha: str, dataset: str | None) -> str:
    """El texto del YAML. `filas`: {cod_dpto, cod_mpio, nom_mpio} del dataset; un departamento fuera de la tabla es un error."""
    nativos = {cod for cod, *_ in DEPARTAMENTOS}
    por_division: dict[str, list[dict]] = defaultdict(list)
    for fila in filas:
        division = str(fila["cod_dpto"]).zfill(2)
        if division not in nativos:
            raise ValueError(f"departamento {division} no está en la tabla de DEPARTAMENTOS: no se inventa")
        por_division[division].append({"codigo_nativo": _Codigo(str(fila["cod_mpio"]).zfill(5)), "nombre": _titulo(fila["nom_mpio"])})

    divisiones = [
        {"iso_3166_2": _Codigo(iso), "codigo_nativo": _Codigo(cod), "nombre_es": es, "nombre_en": en,
         "municipios": sorted(por_division.get(cod, []), key=lambda m: m["codigo_nativo"])}
        for cod, iso, es, en in sorted(DEPARTAMENTOS)
    ]
    encabezado = [
        "# Colombia: divisiones (32 departamentos + Bogotá, D.C.) y municipios. Datos estáticos versionados.",
        "# Fuente oficial: DANE, DIVIPOLA (División Político-Administrativa de Colombia), publicada en datos.gov.co.",
        f"# Dataset: {dataset} (datos.gov.co)." if dataset else "# Dataset: no consultado en esta corrida.",
        f"# Generado el {fecha} por backend/scripts/geografia_co.py. No se edita a mano; no corre en runtime ni en CI.",
        "# iso_3166_2: código ISO 3166-2:CO (común entre países). codigo_nativo: código DIVIPOLA (lo que usan los adaptadores).",
    ]
    if not filas:
        encabezado.append("# ATENCIÓN: sin municipios (la corrida no tuvo red). Correr el script con red para completarlos.")
    cuerpo = yaml.dump({"pais": "CO", "divisiones": divisiones}, Dumper=_Dumper, allow_unicode=True, sort_keys=False)
    return "\n".join(encabezado) + "\n" + cuerpo


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Genera config/geografia/co.yaml desde DIVIPOLA (datos.gov.co).")
    p.add_argument("--sin-municipios", action="store_true", help="solo los departamentos; no sale a la red")
    args = p.parse_args(argv)

    filas: list[dict] = []
    if not args.sin_municipios:
        respuesta = httpx.get(URL.format(dataset=DATASET), timeout=60, params={
            "$select": "cod_dpto,cod_mpio,nom_mpio", "$limit": "50000", "$order": "cod_mpio"})
        respuesta.raise_for_status()
        filas = respuesta.json()
        if not filas:
            print("el dataset no devolvió filas: no se escribe nada", file=sys.stderr)
            return 1
    # Ruta y dataset fijos: la línea de comandos no decide dónde se escribe ni qué se consulta.
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(construir(filas, date.today().isoformat(), None if args.sin_municipios else DATASET))
    print(f"escrito {SALIDA} ({len(filas)} municipios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
