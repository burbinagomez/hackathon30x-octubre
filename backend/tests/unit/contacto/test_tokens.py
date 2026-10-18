import base64
from uuid import uuid4

from app.modulos.contacto.dominio import tokens

CLAVE = b"k" * 32
TENANT, CONTACTO = uuid4(), uuid4()


def test_ida_y_vuelta():
    t = tokens.firmar(CLAVE, "baja", TENANT, CONTACTO)
    assert tokens.verificar(CLAVE, "baja", t) == (TENANT, CONTACTO)


def test_un_bit_cambiado_falla():
    crudo = bytearray(base64.urlsafe_b64decode(tokens.firmar(CLAVE, "baja", TENANT, CONTACTO) + "=="))
    for i in range(len(crudo)):
        roto = crudo.copy()
        roto[i] ^= 1
        assert tokens.verificar(CLAVE, "baja", base64.urlsafe_b64encode(roto).decode().rstrip("=")) is None


def test_proposito_distinto_falla():
    t = tokens.firmar(CLAVE, "msgid", TENANT, CONTACTO)
    assert tokens.verificar(CLAVE, "msgid", t) == (TENANT, CONTACTO)
    assert tokens.verificar(CLAVE, "baja", t) is None


def test_otro_tenant_falla():
    """Mismo contacto y MAC, otro tenant pegado adelante: el tenant está firmado."""
    t = tokens.firmar(CLAVE, "baja", TENANT, CONTACTO)
    crudo = base64.urlsafe_b64decode(t + "==")
    ajeno = base64.urlsafe_b64encode(uuid4().bytes + crudo[16:]).decode().rstrip("=")
    assert len(crudo) > 32
    assert tokens.verificar(CLAVE, "baja", ajeno) is None


def test_otra_clave_falla():
    t = tokens.firmar(CLAVE, "baja", TENANT, CONTACTO)
    assert tokens.verificar(b"x" * 32, "baja", t) is None


def test_basura_no_explota():
    for t in ["", "a", "!!!!", "a" * 500, "é"]:
        assert tokens.verificar(CLAVE, "baja", t) is None


def test_compara_con_compare_digest(monkeypatch):
    llamadas = []
    original = tokens.hmac.compare_digest
    monkeypatch.setattr(tokens.hmac, "compare_digest", lambda a, b: llamadas.append(1) or original(a, b))
    tokens.verificar(CLAVE, "baja", tokens.firmar(CLAVE, "baja", TENANT, CONTACTO))
    assert llamadas == [1]
