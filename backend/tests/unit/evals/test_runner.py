"""Runner de evals (T010): PASS^k, agregado, determinación, forma antes del juez, k=1, baseline y entorno.

Todo en tmp_path con datos sintéticos: `evals.yaml`, archivos de casos y prompts. `baseline.json` vive al lado
de `evals.yaml`, que el runner recibe con `--config` (default: `backend/evals/evals.yaml`). El juez es
`JuezFalso` vía `fabrica_juez`; los costos, un falso que solo acumula filas (duck typing, sin importar del 002).
Nunca red ni API real: `ANTHROPIC_API_KEY` es un valor falso dentro del mapeo `entorno` inyectado.

Para fijar un baseline con valores que el runner no dejaría escribir (agregado bajo umbral, regresión), el test
lo fija con `--actualizar-baseline` y después reescribe `agregado`/`determinacion` dejando el fingerprint que
calculó el runner: así no importa `evals.fingerprint` (no existe hasta T012).

Rojo hasta T012: `run.main` es un stub que devuelve 99 y no imprime nada; cada test falla en su primer assert.
"""
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

from evals import run
from evals.jueces.falso import JuezFalso
from evals.jueces.puerto import SalidaJuezInvalida

pytestmark = pytest.mark.xfail(strict=True, raises=AssertionError,
                               reason="rojo hasta T012: run.main es un stub que devuelve 99")

ENTORNO = {"ANTHROPIC_API_KEY": "falsa-no-real", "DATABASE_URL": "postgresql://localhost/sintetica"}
ENCAJE = "encaje_icp"
CALIBRACION = "juez_mensaje_calibracion"
SI, NO = 0.9, 0.1  # probabilidades del juez: SI ≥ corte 0.5 > NO

ICP = {"pais": "CO", "ciiu": ["4711"], "departamentos": ["Antioquia"],
       "descripcion": "Minoristas de alimentos con local propio"}
CUERPO_VALIDO = ("Hola, le escribe Ejemplo SAS. Encontramos su contacto en el registro mercantil publico. "
                 "Ofrecemos un piloto de prospeccion para su empresa. ¿Le interesa conversar esta semana? "
                 "Si no quiere recibir mas mensajes responda BAJA. Privacidad: https://ejemplo.invalid/privacidad")


class CostosFalso:
    def __init__(self):
        self.filas = []

    def registrar(self, op) -> None:
        self.filas.append(op)


class JuezDeterminista(JuezFalso):
    # Lo que será jev en la 006: puede bajar a k=1 tras demostrar determinación a k=3.
    determinista_si_se_demuestra = True


def _caso(id_: str, etiqueta: str = "encaja", ciudad: str = "Medellin") -> dict:
    return {"id": id_, "pais": "CO", "actividad": "4711", "ciudad": ciudad, "tipo_titular": "juridica",
            "origen": {"fuente": "croma_supersociedades_co", "as_of": "2026-10-17", "licencia": "sintetica"},
            "etiqueta": etiqueta}


def _dataset(*casos: dict) -> dict:
    return {"icp": ICP, "casos": list(casos)}


def _mensaje(id_: str, cuerpo: str = CUERPO_VALIDO, pertinente: bool = True) -> dict:
    return {"id": id_, "lead": {"nombre": "Panaderia Sintetica SAS", "pais": "CO", "ciudad": "Bogota"},
            "mensaje": {"asunto": "Piloto de prospeccion", "cuerpo": cuerpo, "adjuntos": []},
            "pertinente": pertinente}


def _config(tmp_path: Path, evals: dict[str, dict]) -> Path:
    """evals: nombre → {"datos": contenido del archivo de casos, "prompt": texto, **claves de evals.yaml}."""
    (tmp_path / "jueces").mkdir(exist_ok=True)
    yaml_evals = {}
    for nombre, spec in evals.items():
        spec = dict(spec)
        (tmp_path / f"{nombre}.json").write_text(json.dumps(spec.pop("datos")))
        (tmp_path / "jueces" / f"{nombre}_v1.md").write_text(spec.pop("prompt", f"prompt sintetico de {nombre}"))
        yaml_evals[nombre] = {"juez": "claude", "modelo": "claude-sonnet-5-5", "prompt": f"jueces/{nombre}_v1.md",
                              "casos": f"{nombre}.json", "k": 3, "corte": 0.5, "umbral": 0.70, "tolerancia": 0,
                              **spec}
    ruta = tmp_path / "evals.yaml"
    ruta.write_text(yaml.safe_dump(yaml_evals))
    return ruta


def _encaje(tmp_path: Path, *casos: dict, **cfg) -> Path:
    return _config(tmp_path, {ENCAJE: {"datos": _dataset(*casos), **cfg}})


@dataclass
class Corrida:
    codigo: int
    reporte: dict | None
    fabrica_llamadas: list = field(default_factory=list)

    def eval(self, nombre: str = ENCAJE) -> dict:
        assert self.reporte is not None, f"el runner no imprimió el reporte JSON (codigo {self.codigo})"
        return self.reporte["evals"][nombre]


@pytest.fixture
def correr(capsys):
    def _correr(config: Path, juez, *flags: str, tenant: str | None = "tenant-sintetico",
                entorno: dict = ENTORNO, costos: CostosFalso | None = None) -> Corrida:
        llamadas = []

        def fabrica(nombre_eval, lote_id):
            llamadas.append((nombre_eval, lote_id))
            return juez

        argv = ["--config", str(config), *(["--tenant", tenant] if tenant else []), *flags]
        codigo = run.main(argv, entorno=entorno, fabrica_juez=fabrica,
                          registro_costos=costos if costos is not None else CostosFalso())
        out, err = capsys.readouterr()
        # Ningún valor del entorno sale por stdout ni stderr. Sabotaje: un `print(dict(entorno))` en run.main → rojo acá.
        assert not [v for v in entorno.values() if v in out + err], "run.main imprimió un valor del entorno"
        return Corrida(codigo, json.loads(out) if out.strip() else None, llamadas)
    return _correr


def _juez(secuencias: dict[str, list], clase=JuezFalso) -> JuezFalso:
    return clase(secuencias)


def _todos(ids, valor, k: int = 3) -> dict[str, list]:
    return {i: [valor] * k for i in ids}


def _assert_llamadas(juez: JuezFalso, ids, k: int = 3) -> None:
    # Assert barato: cada caso juzgado llamó k veces, y ninguno más (un id ausente = 0 llamadas).
    assert juez.llamadas == {i: k for i in ids}


def _baseline(config: Path) -> Path:
    return config.parent / "baseline.json"


def _fijar_baseline(correr, config: Path, ids, *, agregado=None, determinacion=None, nombre: str = ENCAJE) -> None:
    """Fija el baseline con todos los casos pasando a k=3 y, si se pide, reescribe sus valores (mismo fingerprint)."""
    juez = _juez(_todos(ids, SI))
    assert correr(config, juez, "--actualizar-baseline").codigo == 0
    if agregado is None and determinacion is None:
        return
    datos = json.loads(_baseline(config).read_text())
    if agregado is not None:
        datos[nombre]["agregado"] = agregado
    if determinacion is not None:
        datos[nombre]["determinacion"] = determinacion
    _baseline(config).write_text(json.dumps(datos))


# --- PASS^k y agregados -------------------------------------------------------------------------------------

def test_caso_pasa_solo_si_pasa_las_tres(tmp_path, correr):
    config = _encaje(tmp_path, _caso("a"), _caso("b"))
    juez = _juez({"a": [0.9, 0.9, 0.3], "b": [0.9, 0.8, 0.7]})

    r = correr(config, juez)

    assert r.eval()["fallidos"] == [{"id": "a", "motivo": "fallo_corrida"}]
    assert r.eval()["agregado"] == 0.5
    assert r.eval()["determinacion"] == 0.5  # b: probabilidades distintas, mismo resultado (pasa) → determinista
    _assert_llamadas(juez, ["a", "b"])


def test_corte_es_probabilidad_mayor_o_igual(tmp_path, correr):
    config = _encaje(tmp_path, _caso("a"), _caso("b"), corte=0.8)
    juez = _juez({"a": [0.8] * 3, "b": [0.79] * 3})

    r = correr(config, juez)

    assert r.eval()["fallidos"] == [{"id": "b", "motivo": "fallo_corrida"}]
    _assert_llamadas(juez, "ab")


def test_agregado_es_fraccion_de_casos_que_pasan(tmp_path, correr):
    config = _encaje(tmp_path, _caso("a"), _caso("b"), _caso("c", "no_encaja"), _caso("d", "no_encaja"))
    juez = _juez({"a": [SI] * 3, "b": [NO] * 3, "c": [NO] * 3, "d": [NO] * 3})

    r = correr(config, juez)

    assert r.eval()["agregado"] == 0.75
    assert r.eval()["n"] == 4
    _assert_llamadas(juez, "abcd")


def test_determinacion_cuenta_casos_con_corridas_coincidentes(tmp_path, correr):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcd"))
    # a: [pasa, pasa, falla] no es determinista; b: [falla, falla, falla] sí; c y d pasan las tres.
    juez = _juez({"a": [SI, SI, NO], "b": [NO] * 3, "c": [SI] * 3, "d": [SI] * 3})

    r = correr(config, juez)

    assert r.eval()["determinacion"] == 0.75
    assert r.eval()["agregado"] == 0.5
    _assert_llamadas(juez, "abcd")


def test_determinacion_excluye_casos_fallidos_por_forma(tmp_path, correr):
    largo = CUERPO_VALIDO + " palabra" * 100
    sin_baja = CUERPO_VALIDO.replace("BAJA", "")
    config = _config(tmp_path, {CALIBRACION: {"datos": [
        _mensaje("m-largo", largo), _mensaje("m-sin-baja", sin_baja), _mensaje("m-a"), _mensaje("m-b")]}})
    juez = _juez({"m-a": [SI] * 3, "m-b": [SI, NO, SI]})

    r = correr(config, juez)

    assert r.eval(CALIBRACION)["determinacion"] == 0.5  # denominador: los 2 juzgados
    assert r.eval(CALIBRACION)["agregado"] == 0.25  # denominador: los 4 casos
    _assert_llamadas(juez, ["m-a", "m-b"])

    # Sin casos juzgados, determinacion es null (y no habilita k=1: ver test_k1_solo_con_determinacion_demostrada).
    config = _config(tmp_path, {CALIBRACION: {"datos": [_mensaje("m-largo", largo), _mensaje("m-sin-baja", sin_baja)]}})
    juez = _juez({})

    r = correr(config, juez)

    assert r.eval(CALIBRACION)["determinacion"] is None
    assert r.eval(CALIBRACION)["agregado"] == 0.0
    _assert_llamadas(juez, [])


# --- Forma y salida inválida --------------------------------------------------------------------------------

def test_forma_falla_no_llama_al_juez(tmp_path, correr):
    cuerpo_120 = " ".join(["palabra"] * 120)
    config = _config(tmp_path, {CALIBRACION: {"datos": [_mensaje("m-largo", cuerpo_120), _mensaje("m-ok")]}})
    juez = _juez({"m-ok": [SI] * 3})

    r = correr(config, juez)

    assert r.eval(CALIBRACION)["fallidos"] == [{"id": "m-largo", "motivo": "forma:palabras"}]
    _assert_llamadas(juez, ["m-ok"])  # m-largo: 0 llamadas


def test_salida_invalida_falla_el_caso_con_motivo(tmp_path, correr):
    config = _encaje(tmp_path, _caso("a"), _caso("b"))
    # Una salida inválida es una corrida fallida; el caso sigue a k corridas y la corrida sigue con el resto.
    juez = _juez({"a": [SalidaJuezInvalida("probabilidad: alta"), SI, SI], "b": [SI] * 3})

    r = correr(config, juez)

    assert r.eval()["fallidos"] == [{"id": "a", "motivo": "juez_salida_invalida"}]
    assert r.eval()["agregado"] == 0.5
    assert r.eval()["determinacion"] == 0.5  # a: la inválida cuenta como "falla" → [falla, pasa, pasa]
    _assert_llamadas(juez, "ab")


@pytest.mark.parametrize("nombre, datos", [
    (ENCAJE, _dataset({**_caso("a"), "etiqueta": None})),
    (CALIBRACION, [{**_mensaje("m-a"), "pertinente": None}]),
    (ENCAJE, _dataset({k: v for k, v in _caso("a").items() if k != "etiqueta"})),
], ids=["etiqueta", "pertinente", "etiqueta_ausente"])
def test_etiqueta_invalida_es_config_invalida(tmp_path, correr, nombre, datos):
    config = _config(tmp_path, {nombre: {"datos": datos}})
    juez = _juez({"a": [SI] * 3, "m-a": [SI] * 3})

    r = correr(config, juez)

    assert r.codigo == 2
    assert r.fabrica_llamadas == []
    _assert_llamadas(juez, [], k=0)


class JuezEspia(JuezFalso):
    def __init__(self, secuencias):
        super().__init__(secuencias)
        self.recibidos = []

    def juzgar(self, tarea, caso):
        self.recibidos.append((tarea, caso))
        return super().juzgar(tarea, caso)


def test_juez_recibe_un_caso_con_icp_y_sin_etiqueta(tmp_path, correr):
    config = _config(tmp_path, {
        ENCAJE: {"datos": _dataset(_caso("a"))},
        CALIBRACION: {"datos": [_mensaje("m-a")]},
    })
    juez = _juez({"a": [SI] * 3, "m-a": [SI] * 3}, JuezEspia)

    r = correr(config, juez)

    assert r.reporte is not None, f"el runner no imprimió el reporte JSON (codigo {r.codigo})"
    # Un caso por llamada, como objeto con clave; la etiqueta (ground truth) nunca llega al juez.
    sin_etiqueta = {k: v for k, v in _caso("a").items() if k != "etiqueta"}
    sin_pertinente = {k: v for k, v in _mensaje("m-a").items() if k != "pertinente"}
    recibidos = sorted(juez.recibidos, key=lambda tarea_caso: tarea_caso[1]["id"])  # sin fijar el orden de los evals
    assert recibidos == [(ENCAJE, {**sin_etiqueta, "icp": ICP})] * 3 + [(CALIBRACION, sin_pertinente)] * 3
    _assert_llamadas(juez, ["a", "m-a"])


def test_reporta_fallidos_con_id_y_motivo(tmp_path, correr):
    sin_baja = CUERPO_VALIDO.replace("BAJA", "")
    config = _config(tmp_path, {
        ENCAJE: {"datos": _dataset(_caso("c-a"), _caso("c-ok"))},
        CALIBRACION: {"datos": [_mensaje("m-sin-baja", sin_baja), _mensaje("m-ok")]},
    })
    juez = _juez({"c-a": [0.9, 0.9, 0.3], "c-ok": [SI] * 3, "m-ok": [SI] * 3})

    r = correr(config, juez)

    assert r.eval(ENCAJE)["fallidos"] == [{"id": "c-a", "motivo": "fallo_corrida"}]
    assert r.eval(CALIBRACION)["fallidos"] == [{"id": "m-sin-baja", "motivo": "forma:opt_out"}]
    _assert_llamadas(juez, ["c-a", "c-ok", "m-ok"])


# --- k --------------------------------------------------------------------------------------------------------

def test_k_menor_a_3_con_juez_llm_es_config_invalida(tmp_path, correr):
    # Baseline a k=3 con determinacion 1.0: lo único que impide k=1 es que el juez es LLM.
    _fijar_baseline(correr, _encaje(tmp_path, _caso("a"), k=3), "a")
    config = _encaje(tmp_path, _caso("a"), k=1)
    juez = _juez({"a": [SI] * 3})  # JuezFalso: determinista_si_se_demuestra = False, como claude

    r = correr(config, juez)

    assert r.codigo == 2
    _assert_llamadas(juez, [], k=0)


def test_k1_solo_con_determinacion_demostrada(tmp_path, correr):
    ids = "abcd"
    casos = [_caso(i) for i in ids]
    k1 = lambda **cfg: _encaje(tmp_path, *casos, k=1, **cfg)  # noqa: E731 — k no entra en el fingerprint
    k3 = lambda: _encaje(tmp_path, *casos, k=3)  # noqa: E731

    # Sin baseline a k=3: k=1 no vale.
    assert correr(k1(), _juez(_todos(ids, SI, 1), JuezDeterminista)).codigo == 2

    # Baseline a k=3 con determinacion 0.75 (a no es determinista): k=1 no vale.
    juez = _juez({"a": [SI, NO, SI], **_todos("bcd", SI)}, JuezDeterminista)
    assert correr(k3(), juez, "--actualizar-baseline").codigo == 0
    assert json.loads(_baseline(k3()).read_text())[ENCAJE]["determinacion"] == 0.75
    assert correr(k1(), _juez(_todos(ids, SI, 1), JuezDeterminista)).codigo == 2

    # Baseline a k=3 con determinacion 1.0: k=1 vale, dos veces, sin volver obsoleto el baseline.
    assert correr(k3(), _juez(_todos(ids, SI), JuezDeterminista), "--actualizar-baseline").codigo == 0
    for _ in range(2):
        juez = _juez(_todos(ids, SI, 1), JuezDeterminista)
        r = correr(k1(), juez)
        assert r.codigo == 0
        assert r.eval()["estado"] == "ok"
        _assert_llamadas(juez, ids, k=1)

    # Un baseline de determinacion 1.0 pero de otro fingerprint (prompt distinto) no habilita k=1.
    juez = _juez(_todos(ids, SI, 1), JuezDeterminista)
    assert correr(k1(prompt="prompt sintetico v2"), juez).codigo == 2
    _assert_llamadas(juez, [], k=0)

    # El baseline solo se fija a k=3: k=1 con --actualizar-baseline sale 2 y no escribe.
    antes = _baseline(k1()).read_bytes()
    juez = _juez(_todos(ids, SI, 1), JuezDeterminista)
    assert correr(k1(), juez, "--actualizar-baseline").codigo == 2
    assert _baseline(k1()).read_bytes() == antes

    # determinacion null (ningún caso juzgado) no habilita k=1.
    datos = json.loads(antes)
    datos[ENCAJE]["determinacion"] = None
    _baseline(k1()).write_text(json.dumps(datos))
    assert correr(k1(), _juez(_todos(ids, SI, 1), JuezDeterminista)).codigo == 2


# --- Baseline -------------------------------------------------------------------------------------------------

def test_igual_al_baseline_sale_0(tmp_path, correr):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcd"))
    _fijar_baseline(correr, config, "abcd")
    juez = _juez(_todos("abcd", SI))

    r = correr(config, juez)

    assert r.codigo == 0
    assert r.eval()["estado"] == "ok"
    assert r.reporte["mejora_sin_fijar"] == []
    _assert_llamadas(juez, "abcd")


def test_baja_respecto_al_baseline_sale_1(tmp_path, correr):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcd"))
    _fijar_baseline(correr, config, "abcd", agregado=0.80)
    juez = _juez({"a": [NO] * 3, **_todos("bcd", SI)})  # 0.75, tolerancia 0

    r = correr(config, juez)

    assert r.codigo == 1
    assert r.eval()["estado"] == "regresion"
    _assert_llamadas(juez, "abcd")


def test_tolerancia_absorbe_una_baja_dentro_del_margen(tmp_path, correr):
    casos = [_caso(i) for i in "abcd"]
    _fijar_baseline(correr, _encaje(tmp_path, *casos), "abcd", agregado=0.80)
    # tolerancia no entra en el fingerprint: cambiarla no vuelve obsoleto el baseline.
    config = _encaje(tmp_path, *casos, tolerancia=0.05)
    juez = _juez({"a": [NO] * 3, **_todos("bcd", SI)})  # 0.75 ≥ 0.80 − 0.05

    r = correr(config, juez)

    assert r.codigo == 0
    assert r.eval()["estado"] == "ok"
    _assert_llamadas(juez, "abcd")


def test_bajo_umbral_sale_1_aunque_no_baje(tmp_path, correr):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcde"))
    _fijar_baseline(correr, config, "abcde", agregado=0.60)
    juez = _juez({"a": [NO] * 3, "b": [NO] * 3, **_todos("cde", SI)})  # 0.60 == baseline, umbral 0.70

    r = correr(config, juez)

    assert r.codigo == 1
    assert r.eval()["estado"] == "bajo_umbral"
    _assert_llamadas(juez, "abcde")


@pytest.mark.parametrize("cambio", [
    {"prompt": "prompt sintetico v2"},
    {"ciudad": "Envigado"},  # dataset
    {"modelo": "claude-otro-modelo"},
    {"corte": 0.4},
    {"umbral": 0.75},
], ids=["prompt", "dataset", "modelo", "corte", "umbral"])
def test_fingerprint_distinto_es_baseline_obsoleto(tmp_path, correr, cambio):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcd"))
    _fijar_baseline(correr, config, "abcd")
    cambio = dict(cambio)
    ciudad = cambio.pop("ciudad", "Medellin")
    config = _encaje(tmp_path, *(_caso(i, ciudad=ciudad) for i in "abcd"), **cambio)
    juez = _juez(_todos("abcd", SI))

    r = correr(config, juez)

    assert r.codigo == 1
    assert r.eval()["estado"] == "baseline_obsoleto"
    _assert_llamadas(juez, "abcd")


def test_sin_baseline_sale_1(tmp_path, correr):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcd"))
    juez = _juez(_todos("abcd", SI))

    r = correr(config, juez)

    assert r.codigo == 1
    assert r.eval()["estado"] == "sin_baseline"
    _assert_llamadas(juez, "abcd")

    # Salvo con --actualizar-baseline: pasa el umbral, lo fija y sale 0.
    juez = _juez(_todos("abcd", SI))
    assert correr(config, juez, "--actualizar-baseline").codigo == 0
    fijado = json.loads(_baseline(config).read_text())[ENCAJE]
    assert (fijado["agregado"], fijado["determinacion"], fijado["k"], fijado["n"], fijado["motivo"]) == (1.0, 1.0, 3, 4, None)
    _assert_llamadas(juez, "abcd")


def test_mejora_no_reescribe_baseline_sin_flag(tmp_path, correr):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcd"))
    _fijar_baseline(correr, config, "abcd", agregado=0.75)
    antes = _baseline(config).read_bytes()
    juez = _juez(_todos("abcd", SI))  # 1.0 > 0.75

    r = correr(config, juez)

    assert r.codigo == 0
    assert _baseline(config).read_bytes() == antes
    assert r.reporte["mejora_sin_fijar"] == [ENCAJE]
    assert r.eval()["estado"] == "ok"
    _assert_llamadas(juez, "abcd")


def test_actualizar_baseline_solo_si_pasa_umbrales(tmp_path, correr):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcd"))
    juez = _juez({"a": [NO] * 3, "b": [NO] * 3, **_todos("cd", SI)})  # 0.5 < umbral 0.70

    r = correr(config, juez, "--actualizar-baseline")

    assert r.codigo == 1
    assert not _baseline(config).exists()
    assert r.eval()["estado"] == "bajo_umbral"
    _assert_llamadas(juez, "abcd")


def test_actualizar_baseline_rechaza_regresion_sin_motivo(tmp_path, correr):
    config = _encaje(tmp_path, *(_caso(i) for i in "abcd"))
    _fijar_baseline(correr, config, "abcd", agregado=0.85)
    antes = _baseline(config).read_bytes()
    baja = lambda: _juez({"a": [NO] * 3, **_todos("bcd", SI)})  # noqa: E731 — 0.75 ≥ umbral 0.70, < 0.85

    r = correr(config, baja(), "--actualizar-baseline")
    assert r.codigo == 1
    assert r.eval()["estado"] == "regresion"
    assert _baseline(config).read_bytes() == antes

    r = correr(config, baja(), "--actualizar-baseline", "--motivo", "dataset re-etiquetado")
    assert r.codigo == 0
    fijado = json.loads(_baseline(config).read_text())[ENCAJE]
    assert (fijado["agregado"], fijado["motivo"]) == (0.75, "dataset re-etiquetado")

    # Lo mismo si baja la determinacion con el agregado igual: baseline 0.75 / 1.0, corrida 0.75 / 0.75.
    _fijar_baseline(correr, config, "abcd", agregado=0.75, determinacion=1.0)
    antes = _baseline(config).read_bytes()
    no_determinista = lambda: _juez({"a": [SI, NO, SI], **_todos("bcd", SI)})  # noqa: E731

    assert correr(config, no_determinista(), "--actualizar-baseline").codigo == 1
    assert _baseline(config).read_bytes() == antes

    assert correr(config, no_determinista(), "--actualizar-baseline", "--motivo", "ruido aceptado").codigo == 0
    fijado = json.loads(_baseline(config).read_text())[ENCAJE]
    assert (fijado["determinacion"], fijado["motivo"]) == (0.75, "ruido aceptado")


def test_actualizar_baseline_obsoleto_no_pide_motivo_aunque_baje(tmp_path, correr):
    casos = [_caso(i) for i in "abcd"]
    _fijar_baseline(correr, _encaje(tmp_path, *casos), "abcd", agregado=0.85)
    viejo = json.loads(_baseline(tmp_path / "evals.yaml").read_text())[ENCAJE]["fingerprint"]
    config = _encaje(tmp_path, *casos, prompt="prompt sintetico v2")  # otro fingerprint: no hay contra qué bajar
    juez = _juez({"a": [NO] * 3, **_todos("bcd", SI)})  # 0.75 ≥ umbral 0.70, < 0.85 del baseline viejo

    r = correr(config, juez, "--actualizar-baseline")

    assert r.codigo == 0
    fijado = json.loads(_baseline(config).read_text())[ENCAJE]
    assert (fijado["agregado"], fijado["motivo"]) == (0.75, None)
    assert fijado["fingerprint"] != viejo
    _assert_llamadas(juez, "abcd")


# --- Varios evals y --eval ------------------------------------------------------------------------------------

def _dos_evals(tmp_path: Path, ids_encaje="ab", ids_calibracion=("m1", "m2")) -> Path:
    return _config(tmp_path, {ENCAJE: {"datos": _dataset(*(_caso(i) for i in ids_encaje))},
                              CALIBRACION: {"datos": [_mensaje(i) for i in ids_calibracion]}})


def test_eval_filtra_un_solo_eval_y_no_toca_los_demas(tmp_path, correr):
    config = _dos_evals(tmp_path)
    _fijar_baseline(correr, config, ["a", "b", "m1", "m2"])
    calibracion_antes = json.loads(_baseline(config).read_text())[CALIBRACION]
    juez = _juez(_todos("ab", SI))  # sin secuencias de calibración: si las juzga, JuezFalso falla

    r = correr(config, juez, "--eval", ENCAJE, "--actualizar-baseline")

    assert r.codigo == 0
    assert set(r.reporte["evals"]) == {ENCAJE}
    assert [nombre for nombre, _ in r.fabrica_llamadas] == [ENCAJE]
    assert json.loads(_baseline(config).read_text())[CALIBRACION] == calibracion_antes
    _assert_llamadas(juez, "ab")


def test_actualizar_con_un_eval_bajo_umbral_no_escribe_ninguno(tmp_path, correr):
    config = _dos_evals(tmp_path, ids_calibracion=("m1", "m2", "m3", "m4"))
    juez = _juez({**_todos("ab", SI), **_todos(["m1", "m2"], SI), **_todos(["m3", "m4"], NO)})  # calibración 0.5

    r = correr(config, juez, "--actualizar-baseline")

    assert r.codigo == 1
    assert r.eval(CALIBRACION)["estado"] == "bajo_umbral"
    assert not _baseline(config).exists()
    _assert_llamadas(juez, ["a", "b", "m1", "m2", "m3", "m4"])


def test_lote_id_es_un_uuid_por_corrida(tmp_path, correr):
    config = _encaje(tmp_path, _caso("a"))

    r1 = correr(config, _juez(_todos("a", SI)))
    r2 = correr(config, _juez(_todos("a", SI)))

    assert r1.reporte is not None and r2.reporte is not None
    uuid.UUID(r1.reporte["lote_id"])
    assert r1.reporte["lote_id"] != r2.reporte["lote_id"]
    # fabrica_juez(nombre_eval, lote_id): recibe el mismo lote del reporte, una vez por eval.
    assert [(n, str(lote)) for n, lote in r1.fabrica_llamadas] == [(ENCAJE, r1.reporte["lote_id"])]


# --- Entorno --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("falta", ["ANTHROPIC_API_KEY", "DATABASE_URL"])
def test_sin_entorno_sale_2_sin_llamar(tmp_path, correr, falta):
    config = _encaje(tmp_path, _caso("a"))
    costos = CostosFalso()
    entorno = {k: v for k, v in ENTORNO.items() if k != falta}

    r = correr(config, _juez(_todos("a", SI)), entorno=entorno, costos=costos)

    assert r.codigo == 2
    assert r.fabrica_llamadas == []
    assert costos.filas == []


def test_sin_tenant_sale_2_sin_llamar(tmp_path, correr):
    config = _encaje(tmp_path, _caso("a"))
    costos = CostosFalso()

    r = correr(config, _juez(_todos("a", SI)), tenant=None, costos=costos)

    assert r.codigo == 2
    assert r.fabrica_llamadas == []
    assert costos.filas == []
