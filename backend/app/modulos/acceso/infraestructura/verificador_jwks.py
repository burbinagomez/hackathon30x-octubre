from uuid import UUID

import jwt

from app.modulos.acceso.dominio.errores import JwksInaccesible, TokenInvalido

ALGORITMOS = ["ES256", "RS256"]  # nunca HS256: con la clave pública como secreto sería confusión de algoritmo
REQUERIDOS = ["exp", "sub", "aud", "iss"]
TIMEOUT_JWKS_SEG = 5


def cliente_jwks(url: str) -> jwt.PyJWKClient:
    """El cliente de producción: caché de claves y un JWKS colgado no deja colgada la API."""
    return jwt.PyJWKClient(url, timeout=TIMEOUT_JWKS_SEG)


class VerificadorJwks:
    """Verifica access tokens de Supabase Auth con las claves públicas del proyecto (JWKS)."""

    def __init__(self, cliente_jwks, issuer: str, audience: str = "authenticated"):
        self._cliente = cliente_jwks
        self._issuer = issuer
        self._audience = audience

    def verificar(self, token: str) -> UUID:
        try:
            clave = self._cliente.get_signing_key_from_jwt(token)
            # El PyJWK entero, no `.key`: PyJWT comprueba que el algoritmo del header corresponda a la clave.
            claims = jwt.decode(token, clave, algorithms=ALGORITMOS, audience=self._audience,
                                issuer=self._issuer, options={"require": REQUERIDOS})
            return UUID(claims["sub"])
        except jwt.PyJWKClientConnectionError:
            raise JwksInaccesible() from None
        except (jwt.PyJWTError, ValueError):
            raise TokenInvalido() from None
