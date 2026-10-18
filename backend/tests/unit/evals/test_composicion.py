"""Composición real de evals.run (T019) por la costura `transporte`: JuezClaude del CATALOGO, sin red.

La key sale del mapeo `entorno` de main(), nunca del entorno del proceso. Datos sintéticos, key falsa.
"""
import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from evals import run
from evals.config import cargar
from tests.anthropic_falso import CLAVE_FALSA, transporte
from tests.evals_falso import CASOS, K, config
from tests.falsos import RegistroCostosFalso

# DATABASE_URL a un puerto cerrado: si la composición ignorara el registro inyectado y conectara, no habría filas acá.
ENTORNO = {"ANTHROPIC_API_KEY": CLAVE_FALSA, "DATABASE_URL": "postgresql+psycopg://nadie@127.0.0.1:1/sintetica"}


def correr(capsys, ruta: Path, tenant: str, **kw):
    capturados, cabeceras = [], []
    codigo = run.main(["--config", str(ruta), "--tenant", tenant], entorno=ENTORNO,
                      transporte=transporte(capturados, cabeceras=cabeceras), **kw)
    out, err = capsys.readouterr()
    assert CLAVE_FALSA not in out + err  # ni el reporte ni los errores llevan la key
    return codigo, (json.loads(out) if out.strip() else None), capturados, cabeceras


def test_usa_el_registro_costos_inyectado(tmp_path, capsys):
    costos = RegistroCostosFalso()
    codigo, reporte, capturados, cabeceras = correr(capsys, config(tmp_path), str(uuid4()), registro_costos=costos)

    assert len(costos.filas) == 2 * K * len(CASOS)  # in + out por llamada, todas en el registro inyectado
    assert len(capturados) == K * len(CASOS)
    assert {c["x-api-key"] for c in cabeceras} == {CLAVE_FALSA}  # la key del mapeo `entorno`
    assert {f.lote_id for f in costos.filas} == {UUID(reporte["lote_id"])}
    assert reporte["evals"]["encaje_icp"]["agregado"] == 1.0  # el transporte responde 0.8 y los casos encajan
    assert codigo == 1  # sin baseline


def test_tarifa_del_yaml_entra_como_decimal_de_str(tmp_path, capsys):
    # tarifas.yaml: claude-haiku-5-5 { in_usd_por_M: 0.10, out_usd_por_M: 0.50 }. Decimal(0.10)/1_000_000 no da exacto.
    costos = RegistroCostosFalso()
    correr(capsys, config(tmp_path, modelo="claude-haiku-5-5"), str(uuid4()), registro_costos=costos)

    assert {(f.tipo, f.costo_unitario) for f in costos.filas} == {("llm_tokens_in", Decimal("0.0000001")),
                                                                  ("llm_tokens_out", Decimal("0.0000005"))}


@pytest.mark.parametrize("tenant, modelo, juez", [
    ("no-es-uuid", "claude-sonnet-5-5", "claude"),
    (None, "claude-sin-tarifa", "claude"),
    (None, "claude-sonnet-5-5", "falso"),  # JuezFalso no se arma desde evals.yaml
], ids=["tenant_no_uuid", "modelo_sin_tarifa", "juez_no_componible"])
def test_composicion_invalida_sale_2_sin_llamar(tmp_path, capsys, tenant, modelo, juez):
    costos = RegistroCostosFalso()
    codigo, reporte, capturados, _ = correr(capsys, config(tmp_path, modelo, juez), tenant or str(uuid4()),
                                            registro_costos=costos)

    assert (codigo, reporte, capturados, costos.filas) == (2, None, [], [])


@pytest.mark.parametrize("http", [
    httpx.Response(401, json={"error": {"type": "authentication_error", "message": f"invalid x-api-key {CLAVE_FALSA}"}}),
    httpx.Response(503, text=f"overloaded {CLAVE_FALSA}"),
    httpx.ConnectTimeout("timeout"),
], ids=["401", "503", "connect_timeout"])
def test_falla_del_juez_sale_2_sin_key_ni_costos(tmp_path, capsys, http):
    # Falla de la API, no del modelo: exit 2 (no se pudo evaluar), nunca 1 (regresión) ni un traceback.
    costos, capturados = RegistroCostosFalso(), []
    try:
        codigo = run.main(["--config", str(config(tmp_path)), "--tenant", str(uuid4())], entorno=ENTORNO,
                          registro_costos=costos, transporte=transporte(capturados, http=http))
    except Exception as e:  # noqa: BLE001  el rojo tiene que ser por assert, no por la excepción que escapa
        codigo = repr(e)
    out, err = capsys.readouterr()

    assert codigo == 2
    assert CLAVE_FALSA not in out + err + str(codigo)
    assert costos.filas == [] and len(capturados) == 1  # corta en la primera falla: no sigue gastando


def test_evals_yaml_real_declara_encaje_icp():
    """T022: la entrada versionada; el prompt existe y el modelo tiene tarifa (si no, componer sale 2)."""
    ruta = Path(run.__file__).parent / "evals.yaml"
    assert ruta.is_file()
    cfg = cargar(ruta)["encaje_icp"]

    assert cfg == {"juez": "claude", "modelo": "claude-sonnet-5-5", "prompt": "jueces/encaje_v1.md",
                   "casos": "dataset.json", "k": 3, "corte": 0.5, "umbral": 0.70, "tolerancia": 0}
    assert (ruta.parent / cfg["prompt"]).is_file()
    assert cfg["modelo"] in run._tarifas_llm()
