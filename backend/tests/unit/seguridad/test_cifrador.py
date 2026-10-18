from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import ValidationError

from app.config import ConfigInvalida, Settings
from app.seguridad.cifrado import Cifrador
from tests.conftest import nueva_clave_de_cifrado

NOMBRE = "Tienda Doña Rosa"  # sintético
TENANT, LEAD = uuid4(), uuid4()


@pytest.fixture
def cifrador(clave_cifrado):
    return Cifrador(clave_cifrado)


def test_ida_y_vuelta(cifrador):
    blob = cifrador.cifrar("nombre_cifrado", NOMBRE, TENANT, LEAD)
    assert cifrador.descifrar("nombre_cifrado", blob, TENANT, LEAD) == NOMBRE


def test_el_blob_no_trae_el_texto_y_mide_mas_que_nonce_mas_etiqueta(cifrador):
    blob = cifrador.cifrar("nombre_cifrado", NOMBRE, TENANT, LEAD)
    assert NOMBRE.encode() not in blob
    assert len(blob) == 12 + len(NOMBRE.encode()) + 16  # nonce + texto + etiqueta GCM


def test_nonce_distinto_en_cada_cifrado(cifrador):
    a = cifrador.cifrar("nombre_cifrado", NOMBRE, TENANT, LEAD)
    b = cifrador.cifrar("nombre_cifrado", NOMBRE, TENANT, LEAD)
    assert a != b and a[:12] != b[:12]


def test_aad_de_nombre_y_direccion_no_se_intercambian(cifrador):
    de_nombre = cifrador.cifrar("nombre_cifrado", NOMBRE, TENANT, LEAD)
    de_direccion = cifrador.cifrar("direccion_cifrada", "Calle 1 # 2-3", TENANT, LEAD)
    with pytest.raises(InvalidTag):
        cifrador.descifrar("direccion_cifrada", de_nombre, TENANT, LEAD)
    with pytest.raises(InvalidTag):
        cifrador.descifrar("nombre_cifrado", de_direccion, TENANT, LEAD)


@pytest.mark.parametrize("otro", [
    {"lead_id": uuid4()},
    {"tenant_id": uuid4()},
], ids=["otro_lead", "otro_tenant"])
def test_aad_de_otra_fila_no_descifra(cifrador, otro):
    blob = cifrador.cifrar("nombre_cifrado", NOMBRE, TENANT, LEAD)
    with pytest.raises(InvalidTag):
        cifrador.descifrar("nombre_cifrado", blob, **{"tenant_id": TENANT, "lead_id": LEAD, **otro})


def test_otra_clave_no_descifra(cifrador):
    blob = cifrador.cifrar("nombre_cifrado", NOMBRE, TENANT, LEAD)
    with pytest.raises(InvalidTag):
        Cifrador(nueva_clave_de_cifrado()).descifrar("nombre_cifrado", blob, TENANT, LEAD)


@pytest.mark.parametrize("clave", [None, "", "no-es-base64!", "YWJj"], ids=["none", "vacia", "no_base64", "corta"])
def test_cifrador_falla_sin_una_clave_de_32_bytes(clave):
    with pytest.raises(ConfigInvalida) as exc:
        Cifrador(clave)
    assert "CIFRADO_KEY" in str(exc.value)
    assert clave is None or clave == "" or clave not in str(exc.value)


def test_la_app_no_arranca_sin_cifrado_key(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app_rt@localhost/db")
    monkeypatch.delenv("CIFRADO_KEY")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "cifrado_key" in str(exc.value)


def test_settings_rechaza_una_clave_invalida_sin_filtrar_su_valor(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app_rt@localhost/db")
    monkeypatch.setenv("CIFRADO_KEY", "clave-invalida-sentinela")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "cifrado_key" in str(exc.value)
    assert "clave-invalida-sentinela" not in str(exc.value)
