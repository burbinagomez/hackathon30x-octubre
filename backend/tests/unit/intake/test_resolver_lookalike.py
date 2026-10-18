"""ResolverLookalike con un BuscadorRazonSocial falso. El caso de uso no escribe costos: solo pasa el contexto."""
from dataclasses import dataclass
from uuid import UUID

import pytest

from app.modulos.intake.aplicacion.resolver_lookalike import ResolverLookalike
from app.modulos.intake.dominio.errores import IntakeFueraDeRango

CAMARAS = {"04": "11", "14": "25"}


@dataclass(frozen=True)
class M:
    nit: str
    ciiu: str | None = "4711"
    camara: str | None = "04"
    estado_matricula: str | None = "ACTIVA"


class BuscadorFalso:
    def __init__(self, respuestas: dict[str, list[M]] | None = None, por_defecto: list[M] | None = None):
        self.respuestas = respuestas or {}
        self.por_defecto = por_defecto if por_defecto is not None else [M("900000001")]
        self.llamadas: list[tuple[str, object]] = []

    def buscar_coincidencias(self, nombre_normalizado, contexto_costo):
        self.llamadas.append((nombre_normalizado, contexto_costo))
        return self.respuestas.get(nombre_normalizado, self.por_defecto)


def NOMBRES(n=5):
    return [f"Empresa Ficticia {chr(65 + i)} S.A.S." for i in range(n)]


def _resolver(buscador, **kw):
    return ResolverLookalike(buscador, CAMARAS, **kw)


def test_deduplica_nombres_repetidos_antes_de_consultar():
    b = BuscadorFalso()
    nombres = NOMBRES(5) + ["EMPRESA FICTICIA A SAS", "empresa ficticia a"]
    _resolver(b).ejecutar(nombres)
    consultados = [n for n, _ in b.llamadas]
    assert len(consultados) == 5 and len(set(consultados)) == 5


def test_normaliza_antes_de_consultar():
    b = BuscadorFalso()
    _resolver(b).ejecutar(["Almacenes Éxito S.A."] + NOMBRES(4))
    assert b.llamadas[0][0] == "almacenes exito"


def test_no_resueltos_no_entran_a_la_distribucion():
    nombres = NOMBRES(5)
    b = BuscadorFalso({
        "empresa ficticia a": [],  # 0 matches
        "empresa ficticia b": [M("900000002", ciiu="4719"), M("900000003", ciiu="4719")],  # 2+ matches
        "empresa ficticia c": [M("900000004", ciiu="4711")],
        "empresa ficticia d": [M("900000005", ciiu="4711")],
        "empresa ficticia e": [M("900000006", ciiu="4719")],
    })
    r = _resolver(b).ejecutar(nombres)
    assert r.no_resueltos == [nombres[0], nombres[1]]
    assert r.resueltos == 3
    assert r.distribucion.ciiu == (("4711", 2), ("4719", 1))


def test_mismo_nit_en_varias_filas_es_un_match_unico():
    b = BuscadorFalso(por_defecto=[M("900000001"), M("900000001")])
    r = _resolver(b).ejecutar(NOMBRES(5))
    assert r.no_resueltos == [] and r.resueltos == 5
    assert r.distribucion.ciiu == (("4711", 1),)


def test_todas_las_consultas_usan_el_mismo_lote_id_y_fuente_intake():
    b = BuscadorFalso()
    r = _resolver(b).ejecutar(NOMBRES(5))
    contextos = [c for _, c in b.llamadas]
    assert len(contextos) == 5
    assert {c.fuente for c in contextos} == {"intake"}
    assert len({c.lote_id for c in contextos}) == 1
    assert isinstance(contextos[0].lote_id, UUID) and r.lote_id == contextos[0].lote_id


def test_cada_corrida_tiene_su_lote():
    b = BuscadorFalso()
    r1 = _resolver(b).ejecutar(NOMBRES(5))
    r2 = _resolver(b).ejecutar(NOMBRES(5))
    assert r1.lote_id != r2.lote_id


@pytest.mark.parametrize("cuantos", [0, 4, 51])
def test_fuera_de_5_a_50_nombres(cuantos):
    b = BuscadorFalso()
    with pytest.raises(IntakeFueraDeRango):
        _resolver(b).ejecutar([f"Empresa {i}" for i in range(cuantos)])
    assert b.llamadas == []


@pytest.mark.parametrize("cuantos", [5, 50])
def test_los_limites_entran(cuantos):
    _resolver(BuscadorFalso()).ejecutar([f"Empresa {i}" for i in range(cuantos)])


def test_lineas_en_blanco_no_cuentan():
    with pytest.raises(IntakeFueraDeRango):
        _resolver(BuscadorFalso()).ejecutar(NOMBRES(4) + ["", "   "])


def test_nombre_que_normaliza_a_vacio_no_se_consulta_y_queda_no_resuelto():
    b = BuscadorFalso()
    r = _resolver(b).ejecutar(NOMBRES(5) + ["S.A.S."])
    assert "S.A.S." in r.no_resueltos and len(b.llamadas) == 5


def test_usa_el_catalogo_para_el_ciiu_y_las_camaras_para_el_departamento():
    b = BuscadorFalso(por_defecto=[M("900000001", ciiu="9999", camara="14")])
    r = _resolver(b, ciiu_validos={"4711"}).ejecutar(NOMBRES(5))
    assert r.distribucion.sugerencia.ciiu is None
    assert r.distribucion.sugerencia.departamento == "25"
