class TokenInvalido(Exception):
    """El access token no se puede verificar. Nunca lleva el token ni el detalle de por qué: se responde 401 igual."""


class JwksInaccesible(Exception):
    """No se pudo traer el JWKS (red o timeout). No es un token malo: la API responde 503 y falla cerrado."""
