"""Verificador de access tokens de Supabase Auth, sin red: par EC P-256 generado acá y un JWKS local."""
import base64
import hashlib
import hmac
import json
import time
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from app.modulos.acceso.dominio.errores import JwksInaccesible, TokenInvalido
from app.modulos.acceso.infraestructura.verificador_jwks import VerificadorJwks

ISSUER = "https://proyecto.example/auth/v1"
KID = "clave-1"


def _par():
    privada = ec.generate_private_key(ec.SECP256R1())
    return privada, privada.public_key()


PRIVADA, PUBLICA = _par()
OTRA_PRIVADA, _ = _par()


class JwksLocal:
    """Hace lo que PyJWKClient pero con un JWKS en memoria: busca por kid y lanza si no está."""

    def __init__(self, publica):
        jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(publica))
        self._set = jwt.PyJWKSet.from_dict({"keys": [{**jwk, "kid": KID, "alg": "ES256", "use": "sig"}]})

    def get_signing_key_from_jwt(self, token):
        kid = jwt.get_unverified_header(token).get("kid")
        for clave in self._set.keys:
            if clave.key_id == kid:
                return clave
        raise PyJWKClientError("kid desconocido")


@pytest.fixture
def verificador():
    return VerificadorJwks(JwksLocal(PUBLICA), issuer=ISSUER)


def _claims(**cambios):
    base = {"sub": str(uuid4()), "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 3600}
    base.update(cambios)
    return {k: v for k, v in base.items() if v is not None}


def _emitir(claims, clave=PRIVADA, kid=KID, algoritmo="ES256"):
    return jwt.encode(claims, clave, algorithm=algoritmo, headers={"kid": kid})


def _b64(datos: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(datos).encode()).rstrip(b"=").decode()


def _hs256_con_la_publica(claims):
    # Confusión de algoritmo: HS256 usando la clave pública PEM como secreto. PyJWT se niega a firmarlo, así que se arma a mano.
    pem = PUBLICA.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    cuerpo = f"{_b64({'alg': 'HS256', 'typ': 'JWT', 'kid': KID})}.{_b64(claims)}"
    firma = base64.urlsafe_b64encode(hmac.new(pem, cuerpo.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{cuerpo}.{firma}"


def _rs256_con_el_kid_ec(claims):
    # Header RS256 con el kid de la clave EC: el algoritmo del header no coincide con la clave del JWKS. La firma es basura.
    cuerpo = f"{_b64({'alg': 'RS256', 'typ': 'JWT', 'kid': KID})}.{_b64(claims)}"
    return f"{cuerpo}.{base64.urlsafe_b64encode(b'firma-falsa').rstrip(b'=').decode()}"


def _alg_none(claims):
    return f"{_b64({'alg': 'none', 'typ': 'JWT', 'kid': KID})}.{_b64(claims)}."


def _resultado(verificador, token):
    """'TokenInvalido', o lo que aceptó: así un token que pasa es una falla de aserción y no un error de otro tipo."""
    try:
        return verificador.verificar(token)
    except TokenInvalido:
        return "TokenInvalido"
    except JwksInaccesible:
        return "JwksInaccesible"


def test_token_valido_devuelve_sub(verificador):
    sub = uuid4()

    assert _resultado(verificador, _emitir(_claims(sub=str(sub)))) == sub
    assert type(_resultado(verificador, _emitir(_claims(sub=str(sub))))) is UUID


CASOS_INVALIDOS = {
    "vencido": lambda: _emitir(_claims(exp=int(time.time()) - 10)),
    "sin_exp": lambda: _emitir(_claims(exp=None)),
    "sin_sub": lambda: _emitir(_claims(sub=None)),
    "aud_distinto": lambda: _emitir(_claims(aud="anon")),
    "iss_distinto": lambda: _emitir(_claims(iss="https://otro.example/auth/v1")),
    "otra_clave": lambda: _emitir(_claims(), clave=OTRA_PRIVADA),
    "alg_none": lambda: _alg_none(_claims()),
    "alg_rs256_con_kid_ec": lambda: _rs256_con_el_kid_ec(_claims()),
    "hs256_con_la_clave_publica": lambda: _hs256_con_la_publica(_claims()),
    "kid_desconocido": lambda: _emitir(_claims(), kid="otro"),
    "no_es_un_jwt": lambda: "basura",
}


@pytest.mark.parametrize("caso", sorted(CASOS_INVALIDOS))
def test_token_invalido_lanza(verificador, caso):
    assert _resultado(verificador, CASOS_INVALIDOS[caso]()) == "TokenInvalido"


@pytest.mark.parametrize("sub", ["no-es-uuid", "", "123"])
def test_sub_que_no_es_uuid_lanza(verificador, sub):
    assert _resultado(verificador, _emitir(_claims(sub=sub))) == "TokenInvalido"


class JwksCaido:
    """El JWKS no responde: lo que lanza PyJWKClient cuando falla la red o el timeout."""

    def get_signing_key_from_jwt(self, token):
        raise PyJWKClientConnectionError("sin red")


def test_jwks_inaccesible_no_es_token_invalido():
    # Es un 503 (el servicio no puede verificar), no un 401 (el token está mal): la API los distingue por el tipo.
    verificador = VerificadorJwks(JwksCaido(), issuer=ISSUER)

    assert _resultado(verificador, _emitir(_claims())) == "JwksInaccesible"
    assert not issubclass(JwksInaccesible, TokenInvalido)
