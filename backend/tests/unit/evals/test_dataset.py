"""Esquema y whitelist de los JSON de evals/. El repo es público: nada de contacto ni de Croma identificable.

Primero los chequeos contra fixtures sintéticos en tmp_path (prueban que las reglas no nacen muertas);
después los que leen los JSON reales, marcados xfail estricto hasta que exista el dataset etiquetado (T024).
Esta carpeta va SIN __init__.py: con uno, pytest la importa como paquete `evals` y tapa al real.
"""
import copy
import json
import subprocess
from pathlib import Path

import pytest

from evals import esquema

EVALS = Path(__file__).resolve().parents[3] / "evals"

CROMA = "croma_supersociedades_co"
OSM = "osm_overpass"
ROJO_HASTA_T024 = pytest.mark.xfail(strict=True, raises=AssertionError, reason="rojo hasta T024")


def _caso_croma(i: int, etiqueta: str) -> dict:
    return {
        "id": f"c-abababab{i:04x}",
        "pais": "CO",
        "actividad": "4711",
        "departamento": "Antioquia",
        "ciudad": "Medellin",
        "rango_ingresos": "mediana",
        "tipo_titular": "juridica",
        "origen": {"fuente": CROMA, "as_of": "2026-10-17",
                   "licencia": "datos publicos via Croma; no redistribuir"},
        "etiqueta": etiqueta,
    }


def _caso_osm(i: int, etiqueta: str) -> dict:
    return {
        "id": f"o-cdcdcdcd{i:04x}",
        "pais": "CO",
        "actividad": "panaderia",
        "ciudad": "Bogota",
        "tipo_titular": "juridica",
        "nombre": f"Panaderia Sintetica {i} SAS",
        "origen": {"fuente": OSM, "as_of": "2026-10-17", "licencia": "ODbL"},
        "etiqueta": etiqueta,
    }


def _dataset() -> dict:
    """Dataset sintético válido: 20 casos, 10 de cada etiqueta, mitad Croma, mitad OSM."""
    casos = [_caso_croma(i, "encaja") for i in range(5)]
    casos += [_caso_osm(i, "encaja") for i in range(5, 10)]
    casos += [_caso_croma(i, "no_encaja") for i in range(10, 15)]
    casos += [_caso_osm(i, "no_encaja") for i in range(15, 20)]
    return {
        "icp": {"pais": "CO", "ciiu": ["4711"], "departamentos": ["Antioquia"],
                "descripcion": "Minoristas de alimentos con local propio"},
        "casos": casos,
    }


def _baseline() -> dict:
    return {"encaje_icp": {"agregado": 0.75, "determinacion": 1.0, "k": 3, "n": 20,
                           "fingerprint": "9" * 64, "fecha": "2026-10-17T12:00:00+00:00",
                           "motivo": None}}


def _por_json(tmp_path: Path, datos):
    # Ida y vuelta por un archivo: los números llegan como los deja json (int, float), igual que los reales.
    archivo = tmp_path / "fixture.json"
    archivo.write_text(json.dumps(datos))
    return json.loads(archivo.read_text())


def _reglas(problemas: list[str]) -> set[str]:
    return {p.split(":", 1)[0] for p in problemas}


def _con(datos: dict, i: int = 0, **cambios) -> dict:
    """Copia del dataset con cambios en el caso i (el 0 es de Croma, el 5 de OSM). None borra la clave."""
    d = copy.deepcopy(datos)
    for clave, valor in cambios.items():
        if valor is None:
            d["casos"][i].pop(clave, None)
        else:
            d["casos"][i][clave] = valor
    return d


def _contacto(tmp_path, datos, archivo="dataset.json") -> set[str]:
    return _reglas(esquema.problemas_contacto(archivo, _por_json(tmp_path, datos)))


def _dataset_reglas(tmp_path, datos) -> set[str]:
    return _reglas(esquema.problemas_dataset(_por_json(tmp_path, datos)))


# --- Fixtures sintéticos ---------------------------------------------------------------------

def test_dataset_sintetico_valido_no_tiene_problemas(tmp_path):
    datos = _por_json(tmp_path, _dataset())

    assert esquema.problemas_contacto("dataset.json", datos) == []
    assert esquema.problemas_dataset(datos) == []


@pytest.mark.parametrize("clave", ["email", "telefono", "web", "whatsapp", "nit", "correo", "celular", "Email"])
def test_clave_de_contacto_falla_por_whitelist(tmp_path, clave):
    assert "clave" in _contacto(tmp_path, _con(_dataset(), **{clave: "x"}))


def test_whitelist_es_por_nivel(tmp_path):
    # nombre vale en el caso, no en origen ni en icp: la whitelist no es plana.
    en_origen = _dataset()
    en_origen["casos"][5]["origen"]["nombre"] = "Panaderia Sintetica SAS"
    en_icp = _dataset()
    en_icp["icp"]["nombre"] = "Panaderia Sintetica SAS"
    en_raiz = _dataset()
    en_raiz["pais"] = "CO"

    assert "clave" in _contacto(tmp_path, en_origen)
    assert "clave" in _contacto(tmp_path, en_icp)
    assert "clave" in _contacto(tmp_path, en_raiz)


def test_archivo_sin_whitelist_falla(tmp_path):
    # Un JSON nuevo en evals/ no pasa hasta que alguien escriba su whitelist.
    assert "archivo" in _contacto(tmp_path, {}, archivo="otro.json")


def test_regex_de_telefono_en_notas(tmp_path):
    reglas = _contacto(tmp_path, _con(_dataset(), notas="llamar al 300 123 4567"))

    # notas falla por clave Y por regex: la regex no puede depender de que la clave esté prohibida.
    assert {"clave", "telefono"} <= reglas


@pytest.mark.parametrize("telefono", [
    "+573001234567", "+57 300 123 4567", "300-123-4567", "(601) 234 5678", "300.123.4567",
])
def test_regex_de_telefono_con_separadores(tmp_path, telefono):
    assert "telefono" in _contacto(tmp_path, _con(_dataset(), ciudad=f"Medellin {telefono}"))


@pytest.mark.parametrize("email", ["ventas@ejemplo.com", "VENTAS@EJEMPLO.COM"])
def test_regex_de_email(tmp_path, email):
    assert "email" in _contacto(tmp_path, _con(_dataset(), ciudad=f"escribir a {email}"))


def test_coma_no_es_separador_de_telefono(tmp_path):
    datos = _dataset()
    datos["icp"]["descripcion"] = "CIIU 4711, 4719"

    assert _contacto(tmp_path, datos) == set()


def test_regex_de_telefono_sobre_numeros(tmp_path):
    entero = _con(_dataset(), ingresos=900123456)
    flotante = _con(_dataset(), ingresos=900123456.0)
    baseline_fraccion = _baseline()
    baseline_fraccion["encaje_icp"]["agregado"] = 11 / 15  # 0.7333333333333333: solo cuenta la parte entera

    assert "telefono" in _contacto(tmp_path, entero)
    assert "telefono" in _contacto(tmp_path, flotante)
    assert esquema.problemas_contacto("baseline.json", _por_json(tmp_path, baseline_fraccion)) == []


def test_exentos_cerrados(tmp_path):
    fecha_ok = _dataset()
    fecha_ok["casos"][0]["origen"]["as_of"] = "2026-10-17"
    fecha_tel = _dataset()
    fecha_tel["casos"][0]["origen"]["as_of"] = "300 123 4567"
    fecha_basica = _dataset()
    fecha_basica["casos"][0]["origen"]["as_of"] = "20261017"  # ISO básico: fromisoformat lo acepta, el esquema no
    baseline_tel = _baseline()
    baseline_tel["encaje_icp"]["motivo"] = "3001234567"
    fingerprint_tel = _baseline()
    fingerprint_tel["encaje_icp"]["fingerprint"] = "3001234567"
    motivo_con_fecha = _baseline()
    motivo_con_fecha["encaje_icp"]["motivo"] = "baseline bajado el 2026-10-17"

    assert _contacto(tmp_path, fecha_ok) == set()
    assert "telefono" in _contacto(tmp_path, fecha_tel)
    assert "telefono" in _contacto(tmp_path, fecha_basica)
    # fingerprint de 64 hex y fecha ISO quedan exentos; motivo no lo está, pero una fecha adentro no es teléfono.
    assert _contacto(tmp_path, _baseline(), "baseline.json") == set()
    assert "telefono" in _contacto(tmp_path, baseline_tel, "baseline.json")
    assert "telefono" in _contacto(tmp_path, fingerprint_tel, "baseline.json")
    assert _contacto(tmp_path, motivo_con_fecha, "baseline.json") == set()


def test_id_exento_solo_con_formato_aleatorio(tmp_path):
    assert "telefono" in _contacto(tmp_path, _con(_dataset(), 5, id="900123456"))


def test_nombre_solo_en_juridica_de_osm(tmp_path):
    osm_desconocido = _con(_dataset(), 5, tipo_titular="desconocido")
    croma_con_nombre = _con(_dataset(), nombre="Comercializadora Sintetica SAS")

    assert "nombre" not in _dataset_reglas(tmp_path, _dataset())
    assert "nombre" in _dataset_reglas(tmp_path, osm_desconocido)
    assert "nombre" in _dataset_reglas(tmp_path, croma_con_nombre)


@pytest.mark.parametrize("fuente", ["datos_gov_co_rues", "sitio_web"])
def test_nombre_de_fuente_no_redistribuible_falla(tmp_path, fuente):
    datos = _dataset()
    datos["casos"][5]["origen"]["fuente"] = fuente  # juridica y con nombre

    assert "nombre" in _dataset_reglas(tmp_path, datos)


@pytest.mark.parametrize("fuente", ["supersociedades_co", "croma", "osm", "croma_inventada_co", "limites"])
def test_origen_fuente_es_conjunto_cerrado(tmp_path, fuente):
    datos = _dataset()
    datos["casos"][0]["origen"]["fuente"] = fuente

    assert "origen" in _dataset_reglas(tmp_path, datos)


@pytest.mark.parametrize("id_malo", ["c-123", "900123456", "c-ABABABABABAB", "c-abababababab0"])
def test_croma_id_aleatorio(tmp_path, id_malo):
    assert "croma_id" in _dataset_reglas(tmp_path, _con(_dataset(), id=id_malo))


def test_croma_sin_nueve_digitos_seguidos(tmp_path):
    en_licencia = _dataset()
    en_licencia["casos"][0]["origen"]["licencia"] = "Croma 900123456"

    assert "croma_digitos" in _dataset_reglas(tmp_path, _con(_dataset(), ciudad="Medellin 900123456"))
    assert "croma_digitos" in _dataset_reglas(tmp_path, en_licencia)
    assert esquema.problemas_dataset(_por_json(tmp_path, _dataset())) == []


def test_rango_ingresos_es_enum(tmp_path):
    for rango in ("micro", "pequena", "mediana", "grande"):
        assert "rango_ingresos" not in _dataset_reglas(tmp_path, _con(_dataset(), rango_ingresos=rango))

    assert "rango_ingresos" in _dataset_reglas(tmp_path, _con(_dataset(), rango_ingresos="1.500M"))


@pytest.mark.parametrize(("cop", "rango"), [
    (0, "micro"),
    (999_999_999, "micro"),
    (1_000_000_000, "pequena"),
    (9_999_999_999, "pequena"),
    (10_000_000_000, "mediana"),
    (50_000_000_000, "mediana"),
    (50_000_000_001, "grande"),
])
def test_rango_ingresos_por_cortes_en_cop(cop, rango):
    # En pesos COP (no miles): <1.000M micro · 1.000M–<10.000M pequena · 10.000M–50.000M mediana · >50.000M grande.
    assert esquema.rango_ingresos(cop) == rango


def test_estructura_del_dataset(tmp_path):
    def reglas(datos):
        return _dataset_reglas(tmp_path, datos)

    pocos = _dataset()
    pocos["casos"] = pocos["casos"][:19]
    muchos = _dataset()
    muchos["casos"] += [_caso_osm(i, "encaja") for i in range(100, 121)]
    duplicado = _con(_dataset(), id=_dataset()["casos"][1]["id"])
    etiqueta = _con(_dataset(), etiqueta="tal_vez")
    desbalanceado = _dataset()
    for caso in desbalanceado["casos"][:16]:
        caso["etiqueta"] = "encaja"
    sin_descripcion = _dataset()
    del sin_descripcion["icp"]["descripcion"]

    assert "n_casos" in reglas(pocos)
    assert "n_casos" in reglas(muchos)
    assert "id_duplicado" in reglas(duplicado)
    assert "etiqueta" in reglas(etiqueta)
    assert "min_por_etiqueta" in reglas(desbalanceado)
    assert "icp" in reglas(sin_descripcion)


def test_bordes_de_estructura_pasan(tmp_path):
    # Exactamente 40 casos y exactamente 5 de una etiqueta.
    datos = _dataset()
    datos["casos"] = [_caso_osm(i, "encaja") for i in range(35)] + [_caso_croma(i, "no_encaja") for i in range(35, 40)]

    assert esquema.problemas_dataset(_por_json(tmp_path, datos)) == []


def test_origen_completo_y_as_of_iso(tmp_path):
    sin_licencia = _dataset()
    del sin_licencia["casos"][0]["origen"]["licencia"]
    fecha_local = _dataset()
    fecha_local["casos"][0]["origen"]["as_of"] = "17/10/2026"
    fecha_basica = _dataset()
    fecha_basica["casos"][0]["origen"]["as_of"] = "20261017"

    assert "origen" in _dataset_reglas(tmp_path, sin_licencia)
    assert "origen" in _dataset_reglas(tmp_path, fecha_local)
    assert "origen" in _dataset_reglas(tmp_path, fecha_basica)
    assert "origen" in _dataset_reglas(tmp_path, _con(_dataset(), origen=None))


# --- JSON reales del repo (rojos hasta T024) -------------------------------------------------

def _versionados() -> set[str]:
    r = subprocess.run(["git", "ls-files", "*.json"], cwd=EVALS, capture_output=True, text=True, check=True)
    return set(r.stdout.split())


def _dataset_real() -> dict:
    archivo = EVALS / "dataset.json"
    assert archivo.exists(), "falta backend/evals/dataset.json (lo arma el etiquetado humano, T024)"
    return json.loads(archivo.read_text())


def _reglas_reales() -> set[str]:
    return _reglas(esquema.problemas_dataset(_dataset_real()))


@ROJO_HASTA_T024
def test_dataset_real_valida_contra_esquema():
    assert esquema.problemas_dataset(_dataset_real()) == []


@ROJO_HASTA_T024
def test_cada_caso_tiene_origen():
    assert "origen" not in _reglas_reales()


# dataset.json va siempre (xfail hasta T024); los demás JSON versionados son duros desde que existen.
@pytest.mark.parametrize("archivo", [
    pytest.param("dataset.json", marks=ROJO_HASTA_T024),
    *sorted(_versionados() - {"dataset.json"}),
])
def test_jsons_de_evals_sin_datos_de_contacto(archivo):
    ruta = EVALS / archivo
    assert ruta.exists(), f"falta backend/evals/{archivo}"

    assert esquema.problemas_contacto(archivo, json.loads(ruta.read_text())) == []


@ROJO_HASTA_T024
def test_nombre_solo_en_juridica_de_fuente_redistribuible():
    assert "nombre" not in _reglas_reales()


@ROJO_HASTA_T024
def test_casos_croma_sin_identificador_fiscal():
    assert _reglas_reales() & {"croma_id", "croma_digitos"} == set()


@ROJO_HASTA_T024
def test_licencia_md_atribuye_osm():
    if any(c["origen"]["fuente"] == OSM for c in _dataset_real()["casos"]):
        licencia = (EVALS / "LICENCIA.md").read_text() if (EVALS / "LICENCIA.md").exists() else ""
        assert "© OpenStreetMap contributors" in licencia
        assert "ODbL" in licencia
