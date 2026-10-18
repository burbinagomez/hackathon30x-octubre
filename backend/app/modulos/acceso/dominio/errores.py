class TokenInvalido(Exception):
    """El access token no se puede verificar. Nunca lleva el token ni el detalle de por qué: se responde 401 igual."""
