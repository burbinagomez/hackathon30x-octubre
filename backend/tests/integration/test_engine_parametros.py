import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app import db

NOMBRE = "Tienda Doña Rosa"  # sintético


def test_engine_oculta_los_parametros_en_los_errores(rt, tenants):
    # Una columna inexistente: el error de Postgres no trae la fila, así que lo único que podría filtrar
    # el nombre es el "[parameters: …]" que SQLAlchemy agrega al mensaje.
    with pytest.raises(ProgrammingError) as exc:
        with db.unidad_de_trabajo(rt, tenants["a"]) as c:
            c.execute(text("SELECT columna_que_no_existe FROM leads WHERE ciudad = :n"), {"n": NOMBRE})

    assert "columna_que_no_existe" in str(exc.value)  # el error es el que esperamos
    assert NOMBRE not in str(exc.value) and "[parameters:" not in str(exc.value)
