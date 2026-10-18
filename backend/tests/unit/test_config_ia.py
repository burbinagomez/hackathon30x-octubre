"""IA_API_KEY e IA_MODELO: opcionales en el api. Sin ellas la API arranca y la Puerta B dice 503 ia_no_disponible."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.composicion import cargar_tarifas_llm, ia_configurada
from app.config import SettingsApi

RAIZ = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def entorno_base(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app_rt@localhost/db")
    monkeypatch.setenv("CIFRADO_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://proyecto.example/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_ISSUER", "https://proyecto.example/auth/v1")
    for nombre in ("IA_API_KEY", "IA_MODELO"):
        monkeypatch.delenv(nombre, raising=False)


def test_settings_lee_ia_api_key_e_ia_modelo(monkeypatch):
    monkeypatch.setenv("IA_API_KEY", "sk-ant-valor-secreto")
    monkeypatch.setenv("IA_MODELO", "claude-haiku-5-5")

    s = SettingsApi(_env_file=None)

    assert s.ia_api_key.get_secret_value() == "sk-ant-valor-secreto" and s.ia_modelo == "claude-haiku-5-5"
    assert "sk-ant-valor-secreto" not in repr(s) and "sk-ant-valor-secreto" not in str(s)


def test_sin_ia_los_ajustes_cargan_igual():
    s = SettingsApi(_env_file=None)

    assert s.ia_api_key is None and s.ia_modelo is None


def test_las_variables_de_ia_estan_en_el_env_example_sin_valor():
    lineas = {l.split("=")[0]: l.split("=", 1)[1].split("#")[0].strip()
              for l in (RAIZ / ".env.example").read_text().splitlines() if "=" in l and not l.startswith("#")}

    assert lineas["IA_API_KEY"] == "" and lineas["IA_MODELO"] == ""


def test_los_modelos_con_tarifa_vienen_de_tarifas_yaml_como_decimal():
    from decimal import Decimal

    t = cargar_tarifas_llm()

    assert t["claude-haiku-5-5"] == {"in_usd_por_M": Decimal("0.10"), "out_usd_por_M": Decimal("0.50")}


@pytest.mark.parametrize("key,modelo,esperado", [
    ("sk", "claude-haiku-5-5", True), (None, "claude-haiku-5-5", False), ("sk", None, False), ("sk", "", False),
    ("  ", "claude-haiku-5-5", False), ("sk", "claude-fantasma", False), ("sk", " claude-haiku-5-5 ", True)])
def test_ia_configurada_exige_key_modelo_y_tarifa(key, modelo, esperado):
    ajustes = SimpleNamespace(ia_api_key=None if key is None else SecretStr(key), ia_modelo=modelo)

    assert ia_configurada(ajustes, cargar_tarifas_llm()) is esperado
