from uuid import UUID


class VerificadorJwks:
    """Verifica access tokens de Supabase Auth con las claves públicas del proyecto (JWKS)."""

    def __init__(self, cliente_jwks, issuer: str, audience: str = "authenticated"):
        self._cliente = cliente_jwks
        self._issuer = issuer
        self._audience = audience

    def verificar(self, token: str) -> UUID:
        return UUID(int=0)  # esqueleto T004
