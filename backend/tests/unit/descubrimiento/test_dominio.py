import pytest

from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente, cubre
from app.modulos.descubrimiento.dominio.nit import normalizar_nit


@pytest.mark.parametrize("texto, esperado", [
    ("900.123.456-7", "900123456"),
    ("900123456", "900123456"),
    # Sin guion no se sabe si el último dígito es DV: no se corta (pregunta abierta 8).
    ("9001234567", "9001234567"),
])
def test_normalizar_nit(texto, esperado):
    assert normalizar_nit(texto) == esperado


def _meta(paises):
    return MetaFuente(clave="f", proveedor="p", paises=frozenset(paises),
                      filtros=frozenset({"ciiu", "departamento"}), trae=frozenset(),
                      tipo="dataset", licencia="l")


@pytest.mark.parametrize("paises, criterios, esperado", [
    ({"CO"}, CriteriosICP("CO", {"ciiu": "4711"}), True),
    ({"CO"}, CriteriosICP("MX", {"ciiu": "4711"}), False),
    ({"*"}, CriteriosICP("BR", {"departamento": "11"}), True),
    ({"CO"}, CriteriosICP("CO", {"ciiu": "4711", "partida_arancelaria": "0901"}), True),
], ids=["pais", "otro_pais", "comodin", "filtro_fuera_no_importa"])
def test_cubre(paises, criterios, esperado):
    assert cubre(_meta(paises), criterios) is esperado
