def normalizar_nit(texto: str) -> str:
    """Solo dígitos, sin DV. El DV se corta solo si viene tras '-': sin guion no se sabe cuál es."""
    base = texto.split("-", 1)[0]
    return "".join(c for c in base if c.isdigit())
