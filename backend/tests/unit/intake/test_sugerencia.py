"""validar_sugerencia: la salida cruda de la Puerta B (o de cualquier fuente) -> `Sugerencia` con la forma del body de
PedidoVistaPrevia. Departamento y ciudad salen como lo que la API acepta; lo que no resuelve sale null, nunca texto libre.
Geografía y actividades sintéticas: el dominio recibe los catálogos, no lee archivos."""
import pytest

from app.modulos.intake.dominio.errores import SalidaIntakeInvalida
from app.modulos.intake.dominio.sugerencia import Sugerencia, validar_sugerencia

ANTIOQUIA = {"iso_3166_2": "CO-ANT", "codigo_nativo": "05", "nombre_es": "Antioquia", "nombre_en": "Antioquia",
             "municipios": [{"codigo_nativo": "05001", "nombre": "Medellín"}, {"codigo_nativo": "05088", "nombre": "Bello"}]}
BOGOTA = {"iso_3166_2": "CO-DC", "codigo_nativo": "11", "nombre_es": "Bogotá, D.C.", "nombre_en": "Bogotá, D.C.",
          "municipios": [{"codigo_nativo": "11001", "nombre": "Bogotá, D.C."}]}
VALLE = {"iso_3166_2": "CO-VAC", "codigo_nativo": "76", "nombre_es": "Valle del Cauca", "nombre_en": "Valle del Cauca",
         "municipios": [{"codigo_nativo": "76001", "nombre": "Cali"}, {"codigo_nativo": "76111", "nombre": "Bello"}]}
GEOGRAFIA = {"CO": {"pais": "CO", "divisiones": [ANTIOQUIA, BOGOTA, VALLE]}}
ACTIVIDADES = {"4711": {"nombre_es": "x"}, "4752": {"nombre_es": "y"}}


def crudo(**cambios):
    base = {"pais": "CO", "ciiu": "4752", "departamento": "Antioquia", "ciudad": None, "ingresos_min": 500000000,
            "palabras_clave": ["ferretería"], "exclusiones": ["cadenas"]}
    return {**base, **cambios}


def validar(**cambios):
    return validar_sugerencia(crudo(**cambios), GEOGRAFIA, ACTIVIDADES)


def test_salida_completa_mapea_a_sugerencia_con_codigos():
    s = validar()

    assert s == Sugerencia(pais="CO", ciiu="4752", departamento="05", ciudad=None, ingresos_min=500000000,
                           palabras_clave=("ferretería",), exclusiones=("cadenas",))


@pytest.mark.parametrize("dicho", ["05", "Antioquia", "antioquia", "ANTIOQUIA ", "CO-ANT"])
def test_departamento_se_resuelve_por_codigo_nombre_o_iso(dicho):
    assert validar(departamento=dicho).departamento == "05"


@pytest.mark.parametrize("dicho", ["Bogotá", "bogota", "Bogotá, D.C.", "BOGOTA D.C."])
def test_bogota_resuelve_con_o_sin_sufijo(dicho):
    assert validar(departamento=dicho).departamento == "11"


def test_departamento_que_no_existe_sale_null_y_no_texto_libre():
    s = validar(departamento="Narnia")

    assert s.departamento is None


def test_ciudad_se_resuelve_dentro_de_su_departamento_y_sale_como_nombre_del_municipio():
    s = validar(departamento="Antioquia", ciudad="medellin")

    assert (s.departamento, s.ciudad) == ("05", "Medellín")


def test_ciudad_de_otro_departamento_sale_null():
    s = validar(departamento="Antioquia", ciudad="Cali")

    assert (s.departamento, s.ciudad) == ("05", None)


def test_ciudad_unica_en_el_pais_completa_el_departamento():
    s = validar(departamento=None, ciudad="Cali")

    assert (s.departamento, s.ciudad) == ("76", "Cali")


def test_ciudad_ambigua_sin_departamento_sale_null():
    # Bello existe en Antioquia y (sintético) en Valle: sin departamento no se adivina.
    s = validar(departamento=None, ciudad="Bello")

    assert (s.departamento, s.ciudad) == (None, None)


def test_ciiu_fuera_del_catalogo_sale_null():
    assert validar(ciiu="9999").ciiu is None


def test_ciiu_con_forma_invalida_sale_null():
    assert validar(ciiu="47").ciiu is None


def test_ciiu_entero_se_acepta_como_texto():
    assert validar(ciiu=4711).ciiu == "4711"


def test_pais_faltante_es_salida_invalida():
    salida = crudo()
    del salida["pais"]

    with pytest.raises(SalidaIntakeInvalida):
        validar_sugerencia(salida, GEOGRAFIA, ACTIVIDADES)


@pytest.mark.parametrize("pais", ["Colombia", "co", None, 57, "ZZ"])
def test_pais_fuera_del_enum_es_salida_invalida(pais):
    with pytest.raises(SalidaIntakeInvalida):
        validar(pais=pais)


@pytest.mark.parametrize("cambios", [
    {"ingresos_min": -1}, {"ingresos_min": "mucho"}, {"ingresos_min": True},
    {"palabras_clave": "ferretería"}, {"palabras_clave": [1, 2]}, {"exclusiones": {"a": 1}},
])
def test_formas_que_no_son_las_del_esquema_son_salida_invalida(cambios):
    with pytest.raises(SalidaIntakeInvalida):
        validar(**cambios)


def test_salida_que_no_es_objeto_es_salida_invalida():
    with pytest.raises(SalidaIntakeInvalida):
        validar_sugerencia(["pais", "CO"], GEOGRAFIA, ACTIVIDADES)


def test_palabras_se_recortan_a_lo_que_acepta_la_api():
    s = validar(palabras_clave=[f"p{i}" for i in range(15)] + ["x" * 41, "  ", "p0"], exclusiones=["z" * 41, " mayoristas "])

    assert s.palabras_clave == tuple(f"p{i}" for i in range(10))  # máx. 10, sin vacías, sin repetidas, sin las de >40
    assert s.exclusiones == ("mayoristas",)


def test_ingresos_como_numero_con_decimales_se_trunca_a_entero():
    assert validar(ingresos_min=1500000.0).ingresos_min == 1500000


def test_campos_opcionales_ausentes_quedan_vacios():
    s = validar_sugerencia({"pais": "CO"}, GEOGRAFIA, ACTIVIDADES)

    assert s == Sugerencia(pais="CO", ciiu=None, departamento=None, ciudad=None, ingresos_min=None,
                           palabras_clave=(), exclusiones=())


def test_pais_sin_geografia_deja_departamento_y_ciudad_en_null():
    s = validar(pais="MX", departamento="Antioquia", ciudad="Medellín")

    assert (s.pais, s.departamento, s.ciudad) == ("MX", None, None)


def test_la_sugerencia_se_serializa_con_la_forma_del_body_de_vista_previa():
    assert validar().como_dict() == {
        "pais": "CO", "ciiu": "4752", "departamento": "05", "ciudad": None, "ingresos_min": 500000000,
        "palabras_clave": ["ferretería"], "exclusiones": ["cadenas"]}
