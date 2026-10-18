from fastapi import HTTPException


def sin_implementar() -> None:
    raise HTTPException(status_code=501)
