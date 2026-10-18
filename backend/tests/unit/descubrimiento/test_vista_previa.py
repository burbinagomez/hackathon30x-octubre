"""T024 [MIN]: la vista previa crea el borrador y dice qué fuentes corren, cuáles se descartan y por qué.
Sin `contar` ni costos: eso es Pulido (Fase 4). Todo con fuentes y repo falsos, sin red ni base."""
from decimal import Decimal

from app.modulos.descubrimiento.aplicacion.vista_previa import VistaPrevia
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP, MetaFuente
from tests.falsos import FabricaFalsa, RegistroCostosFalso, RepositorioLeadsFalso

ACTIVIDADES = {"4711": ("shop=supermarket", "shop=convenience")}


def _meta(clave, paises, filtros):
    return MetaFuente(clave=clave, proveedor=clave.split("_")[0], paises=frozenset(paises), filtros=frozenset(filtros),
                      trae=frozenset({"nombre"}), tipo="live", licencia=f"lic_{clave}")


METAS = {
    "croma_supersociedades_co": _meta("croma_supersociedades_co", {"CO"}, {"ciiu", "departamento", "ingresos_min"}),
    "osm_overpass": _meta("osm_overpass", {"CO", "PE"}, {"tipo_negocio", "ciudad"}),
}


def _caso():
    repo, costos = RepositorioLeadsFalso(), RegistroCostosFalso()
    fabrica = FabricaFalsa(costos, METAS)
    return VistaPrevia(repo, fabrica, ACTIVIDADES), repo, fabrica


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
