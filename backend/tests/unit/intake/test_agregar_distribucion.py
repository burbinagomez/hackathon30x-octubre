"""Dominio puro de la Puerta A: sin I/O. Los matches son datos sintéticos."""
from dataclasses import dataclass

from app.modulos.intake.dominio.agregar_distribucion import agregar_distribucion
from app.modulos.intake.dominio.puertos_lookalike import CoincidenciaRues

# cámara -> departamento (lo que arma la composición desde camaras_co.yaml)
CAMARAS = {"04": "11", "14": "25", "47": "25"}


@dataclass(frozen=True)
class M:
    nit: str
    ciiu: str | None = "4711"
    camara: str | None = "04"
    estado_matricula: str | None = "ACTIVA"


def _nits(n: int, desde: int = 900000001):
    return [str(desde + i) for i in range(n)]


def test_cumple_el_protocolo_de_coincidencia():
    assert isinstance(M("900000001"), CoincidenciaRues)


def test_ciiu_mas_frecuente_gana():
    matches = [M(n, ciiu="4711") for n in _nits(6)] + [M(n, ciiu="4719") for n in _nits(4, 900000101)]
    d = agregar_distribucion(matches, CAMARAS)
    assert d.sugerencia.ciiu == "4711"
    assert d.ciiu == (("4711", 6), ("4719", 4))


def test_departamento_mas_frecuente_gana():
    matches = [M(n, camara="14") for n in _nits(3)] + [M(n, camara="04") for n in _nits(5, 900000101)]
    d = agregar_distribucion(matches, CAMARAS)
    assert d.sugerencia.departamento == "11"
    assert d.departamento == (("11", 5), ("25", 3))


def test_explicacion_trae_top_3_con_conteo():
    camaras = {"a": "05", "b": "08", "c": "11", "d": "13", "e": "15"}
    cuentas = {"a": 5, "b": 4, "c": 3, "d": 2, "e": 1}
    matches, desde = [], 900000001
    for cam, n in cuentas.items():
        matches += [M(x, camara=cam, ciiu=f"47{ord(cam) % 10}1") for x in _nits(n, desde)]
        desde += 100
    d = agregar_distribucion(matches, camaras)
    assert d.departamento == (("05", 5), ("08", 4), ("11", 3))
    assert len(d.ciiu) == 3
    assert d.sugerencia.departamento == "05"


def test_empate_se_rompe_por_codigo_y_es_estable():
    matches = [M("900000001", ciiu="4719"), M("900000002", ciiu="4711")]
    a = agregar_distribucion(matches, CAMARAS)
    b = agregar_distribucion(list(reversed(matches)), CAMARAS)
    assert a.sugerencia.ciiu == b.sugerencia.ciiu == "4711"


def test_no_sugiere_ingresos_min():
    d = agregar_distribucion([M(n) for n in _nits(3)], CAMARAS)
    assert d.sugerencia.ingresos_min is None
    assert d.sugerencia.ciudad is None
    assert d.sugerencia.pais == "CO"


def test_sin_matches_da_sugerencia_vacia():
    d = agregar_distribucion([], CAMARAS)
    assert d.sugerencia.ciiu is None and d.sugerencia.departamento is None
    assert d.ciiu == () and d.departamento == ()


def test_matricula_cancelada_no_entra_a_la_distribucion():
    matches = [M("900000001", ciiu="4719", estado_matricula="CANCELADA"), M("900000002", ciiu="4711")]
    d = agregar_distribucion(matches, CAMARAS)
    assert d.ciiu == (("4711", 1),)
    assert d.sugerencia.ciiu == "4711"


def test_mismo_nit_desde_dos_nombres_cuenta_una_vez():
    d = agregar_distribucion([M("900000001"), M("900000001"), M("900000002", ciiu="4719")], CAMARAS)
    assert d.ciiu == (("4711", 1), ("4719", 1))
    assert d.departamento == (("11", 2),)


def test_camara_desconocida_no_suma_al_departamento():
    d = agregar_distribucion([M("900000001", camara="99"), M("900000002", camara=None)], CAMARAS)
    assert d.departamento == ()
    assert d.sugerencia.departamento is None
    assert d.ciiu == (("4711", 2),)  # el CIIU sí cuenta: la cámara no es su dato


def test_ciiu_fuera_del_catalogo_sale_none_pero_la_explicacion_lo_muestra():
    d = agregar_distribucion([M("900000001", ciiu="9999")], CAMARAS, ciiu_validos={"4711"})
    assert d.sugerencia.ciiu is None
    assert d.ciiu == (("9999", 1),)


def test_ciiu_dentro_del_catalogo_se_sugiere():
    d = agregar_distribucion([M("900000001")], CAMARAS, ciiu_validos={"4711"})
    assert d.sugerencia.ciiu == "4711"
