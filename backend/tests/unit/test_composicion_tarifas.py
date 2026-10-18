"""`cargar_tarifas` (T012): suma `dapta`, y un `null` en el yaml se lee como `None`, nunca como `Decimal(0)`."""
from decimal import Decimal
from pathlib import Path

from app.composicion import cargar_tarifas

REAL = Path(__file__).resolve().parents[2] / "config" / "tarifas.yaml"


def test_dapta_lee_la_tarifa_real_del_yaml():
    tarifas = cargar_tarifas(REAL)

    assert tarifas["dapta"] == Decimal("0.333")
    assert type(tarifas["dapta"]) is Decimal


def test_dapta_null_es_none_no_cero(tmp_path):
    yaml_sintetico = tmp_path / "tarifas.yaml"
    yaml_sintetico.write_text(
        "computo_seg_usd: 0.0000070\n"
        "web_fetch_usd: 0.00001\n"
        "croma: { usd_por_credito: 0.00099 }\n"
        "jev: { in_usd_por_M: 0.042 }\n"
        "dapta: { usd_por_minuto: null }\n"
    )

    tarifas = cargar_tarifas(yaml_sintetico)

    assert tarifas["dapta"] is None
