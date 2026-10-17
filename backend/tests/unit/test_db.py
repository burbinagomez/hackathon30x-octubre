import psycopg
import pytest

from app import db


def test_engine_desactiva_prepared_statements(monkeypatch):
    # Supavisor en modo transacción no soporta prepared statements (R10): sin DB, se mira lo que llega a psycopg.
    recibido = {}

    def connect(*args, **kwargs):
        recibido.update(kwargs)
        raise RuntimeError("sin red en unit")

    monkeypatch.setattr(psycopg, "connect", connect)
    with pytest.raises(Exception):
        db.crear_engine("postgresql+psycopg://u@h/d").connect()

    assert "prepare_threshold" in recibido
    assert recibido["prepare_threshold"] is None
