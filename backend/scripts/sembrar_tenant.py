"""Siembra (o actualiza) el tenant del evento. Corre un humano desde local; la URL de postgres va por getpass."""
import getpass  # noqa: F401  el test lo reemplaza con monkeypatch
from uuid import UUID


def sembrar(conexion, tenant_id: UUID, nombre: str, idioma: str) -> None:
    return None


def main(argv=None) -> int:
    return 0
