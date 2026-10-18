import pytest

from app.modulos.intake.dominio.normalizar import normalizar_nombre


@pytest.mark.parametrize("crudo, esperado", [
    ("Almacenes Éxito S.A.", "almacenes exito"),
    ("  ALMACENES   EXITO  ", "almacenes exito"),
    ("Exito S.A.S", "exito"),
    ("Ferretería El Tornillo Ltda.", "ferreteria el tornillo"),
    ("Bavaria & Cía. S.A.", "bavaria cia"),
    ("", ""),
    ("S.A.S.", ""),
    ("Droguería ñandú", "drogueria nandu"),
])
def test_normaliza(crudo, esperado):
    assert normalizar_nombre(crudo) == esperado


def test_mayusculas_y_tildes_dan_la_misma_clave():
    assert normalizar_nombre("ÉXITO") == normalizar_nombre("exito")
