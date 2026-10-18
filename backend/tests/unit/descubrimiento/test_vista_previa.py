"""T024 [MIN]: la vista previa crea el borrador y dice qué fuentes corren, cuáles se descartan y por qué.
Sin `contar` ni costos: eso es Pulido (Fase 4). Todo con fuentes y repo falsos, sin red ni base."""
from decimal import Decimal

from app.modulos.descubrimiento.aplicacion.vista_previa import VistaPrevia
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente
from tests.falsos import FabricaFalsa, RegistroCostosFalso, RepositorioLeadsFalso

ACTIVIDADES = {"4711": ("shop=supermarket", "shop=convenience")}


def _meta(clave, paises, filtros, costo_maximo_llamada=Decimal("0")):
    return MetaFuente(clave=clave, proveedor=clave.split("_")[0], paises=frozenset(paises), filtros=frozenset(filtros),
                      trae=frozenset({"nombre"}), tipo="live", licencia=f"lic_{clave}",
                      costo_maximo_llamada=costo_maximo_llamada)


METAS = {
    "croma_supersociedades_co": _meta("croma_supersociedades_co", {"CO"}, {"ciiu", "departamento", "ingresos_min"},
                                      Decimal("0.00099")),
    "osm_overpass": _meta("osm_overpass", {"CO", "PE"}, {"tipo_negocio", "ciudad"}, Decimal("0.00042")),
}
RUES = _meta("datos_gov_co_rues", {"CO"}, {"ciiu", "departamento"}, Decimal("0.00084"))


def _caso(metas=METAS, costos=None):
    repo, costos = RepositorioLeadsFalso(), costos or RegistroCostosFalso()
    fabrica = FabricaFalsa(costos, metas)
    return VistaPrevia(repo, fabrica, ACTIVIDADES, costos), repo, fabrica


def test_conteo_por_fuente_y_motivo_de_las_descartadas():
    caso, _, _ = _caso()
    criterios = CriteriosICP(pais="PE", filtros={"ciiu": "4711", "ciudad": "Lima"})

    r = caso.ejecutar(criterios, "email", Decimal("5.00"), None)

    assert [f.clave for f in r.fuentes] == ["osm_overpass"]
    assert dict(r.descartadas) == {"croma_supersociedades_co": "pais"}  # código, nunca una frase


def test_ignorados_son_los_criterios_que_la_fuente_no_aplica_y_el_ciiu_traducido_no_cuenta():
    caso, _, _ = _caso()
    # El orden de inserción NO es el alfabético: un `ignorados` que no ordena se delata.
    criterios = CriteriosICP(pais="CO", filtros={"ingresos_min": "1000000", "macrosector": "comercio", "ciiu": "4711",
                                                 "departamento": "Cundinamarca", "ciudad": "Bogotá"})

    r = caso.ejecutar(criterios, "email", Decimal("5.00"), None)

    por_clave = {f.clave: f.ignorados for f in r.fuentes}
    # Croma aplica ciiu, departamento e ingresos_min; ignora ciudad y macrosector (su YAML de prueba no lo declara).
    # OSM aplica ciudad; ignora departamento, ingresos_min y macrosector. El ciiu no cuenta como ignorado:
    # lo aplica traducido a tipo_negocio.
    assert por_clave == {"osm_overpass": ("departamento", "ingresos_min", "macrosector"),
                         "croma_supersociedades_co": ("ciudad", "macrosector")}


def test_crea_busqueda_en_borrador_con_criterios():
    caso, repo, fabrica = _caso()
    criterios = CriteriosICP(pais="CO", filtros={"ciiu": "4711", "ciudad": "Bogotá"})

    r = caso.ejecutar(criterios, "email", Decimal("5.00"), "Hola")

    assert r.busqueda_id is not None
    assert repo.busquedas[r.busqueda_id] == "borrador"  # crear_busqueda del 002 la dejaría en `creada`
    guardado = repo.borradores[r.busqueda_id]
    assert guardado[0] == criterios  # criterios congelados
    assert guardado[1:] == ("email", Decimal("5.00"), "Hola")
    assert type(guardado[2]) is Decimal
    # lote = búsqueda: las fuentes se piden una vez y con el id del borrador, que ya existe.
    assert fabrica.llamadas == [r.busqueda_id]


# --- costo máximo y tope (advisor, costos) --------------------------------------------------------------------

CO = CriteriosICP(pais="CO", filtros={"ciiu": "4711", "ciudad": "Bogotá", "departamento": "Cundinamarca"})


def test_costo_maximo_suma_costo_maximo_llamada_de_cada_fuente():
    caso, _, _ = _caso()

    r = caso.ejecutar(CO, "email", Decimal("5.00"), None)

    assert type(r.costo_maximo_usd) is Decimal
    assert r.costo_maximo_usd == Decimal("0.00141")  # 0.00099 + 0.00042; el libro del lote nuevo está vacío


def test_costo_maximo_incluye_datos_gov_co_rues():
    # Si el cálculo iterara un subconjunto fijo de claves, el tope se calcularía sin este adaptador y nadie lo notaría.
    caso, _, _ = _caso({**METAS, "datos_gov_co_rues": RUES})

    r = caso.ejecutar(CO, "email", Decimal("5.00"), None)

    assert r.costo_maximo_usd == Decimal("0.00225")  # + 2 requests x 2 intentos x 30 s x 0.0000070


def test_costo_maximo_suma_solo_las_fuentes_seleccionadas():
    caso, _, _ = _caso()
    pe = CriteriosICP(pais="PE", filtros={"ciiu": "4711", "ciudad": "Lima"})  # Croma no cubre PE

    r = caso.ejecutar(pe, "email", Decimal("5.00"), None)

    assert r.costo_maximo_usd == Decimal("0.00042")


def test_costo_maximo_incluye_lo_ya_gastado_en_el_lote():
    class LibroConGasto(RegistroCostosFalso):
        def gasto_busqueda(self, busqueda_id):
            return Decimal("0.00113")

    caso, _, _ = _caso(costos=LibroConGasto())

    r = caso.ejecutar(CO, "email", Decimal("5.00"), None)

    assert r.costo_maximo_usd == Decimal("0.00254")  # 0.00113 + 0.00141


def test_dentro_del_tope_es_inclusivo_en_el_borde():
    caso, _, _ = _caso()

    justo = caso.ejecutar(CO, "email", Decimal("0.00141"), None)
    corto = caso.ejecutar(CO, "email", Decimal("0.00140"), None)

    assert justo.dentro_del_tope is True  # <=, no <
    assert corto.dentro_del_tope is False
    assert corto.busqueda_id is not None  # fuera del tope igual crea el borrador: el usuario ajusta y vuelve a pedir


def test_dentro_del_tope_nunca_es_none_con_tope_y_fuentes():
    caso, _, _ = _caso()

    r = caso.ejecutar(CO, "email", Decimal("5.00"), None)

    assert r.dentro_del_tope is True  # null = "no se aplica"; ya se aplica
