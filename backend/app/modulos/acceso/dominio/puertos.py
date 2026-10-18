from typing import Protocol
from uuid import UUID


class VerificadorToken(Protocol):
    def verificar(self, token: str) -> UUID:
        """El `sub` (auth_user_id) del access token, o TokenInvalido."""
        ...
