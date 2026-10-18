def hmac_email(email: str, clave: bytes) -> bytes:
    """HMAC-SHA256 de lower(strip(email)). El email no se guarda: solo esto (principio VI, P13)."""
    return b""  # esqueleto T004
