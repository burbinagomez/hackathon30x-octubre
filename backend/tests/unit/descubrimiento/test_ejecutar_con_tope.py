"""T026 [MIN]: ejecutar un borrador guardado. El tope (y las palabras clave) son Pulido; acá solo lo que el [MIN] necesita
y lo que protege costos y cumplimiento: una ejecución por borrador, criterios congelados, lote = búsqueda, estado final."""
import inspect
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBorrador
from app.modulos.descubrimiento.dominio.errores import BusquedaYaEjecutada, FuenteNoDisponible
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda, MetaFuente
from tests.falsos import FabricaFalsa, RegistroCostosFalso, RepositorioLeadsFalso

AS_OF = datetime(2026, 10, 1, tzinfo=UTC)


def _meta(clave, filtros):
    return MetaFuente(clave=clave, proveedor=clave.split("_")[0], paises=frozenset({"CO"}), filtros=frozenset(filtros),
                      trae=frozenset({"nombre"}), tipo="live", licencia=f"lic_{clave}")


METAS = {
    "croma_supersociedades_co": _meta("croma_supersociedades_co", {"ciiu", "departamento"}),
    "osm_overpass": _meta("osm_overpass", {"tipo_negocio", "departamento"}),
}
ACTIVIDADES = {"1081": ("shop=bakery",)}
GUARDADOS = CriteriosICP(pais="CO", filtros={"ciiu": "1081", "departamento": "Antioquia"})


def _empresa(fuente, nit):
    return EmpresaCruda(pais="CO", nombre=f"EMPRESA {nit} SAS", fuente=fuente, url_origen=f"https://{fuente}.test/{nit}",
                        as_of=AS_OF, actividad=Actividad("1081", "CIIU"), id_fiscal=nit, tipo_titular="juridica")


def _caso(errores=None, empresas=None, repo=None):
    repo, costos = repo or RepositorioLeadsFalso(), RegistroCostosFalso()
    empresas = empresas if empresas is not None else {"croma_supersociedades_co": (_empresa("croma_supersociedades_co", "900000001"),),
                                                       "osm_overpass": (_empresa("osm_overpass", "900000002"),)}
    fabrica = FabricaFalsa(costos, METAS, empresas, errores)
    borrador_id = repo.crear_borrador(GUARDADOS, "email", Decimal("5.00"), None)
    return EjecutarBorrador(repo, fabrica, ACTIVIDADES), repo, costos, fabrica, borrador_id


def test_usa_los_criterios_guardados():
    caso, repo, costos, fabrica, borrador_id = _caso()

    # Sin parámetro de criterios: no hay por dónde colar otros distintos de los congelados en el borrador.
    assert list(inspect.signature(EjecutarBorrador.ejecutar).parameters) == ["self", "busqueda_id"]
    caso.ejecutar(borrador_id)

    assert sorted(fabrica.criterios_recibidos, key=lambda c: sorted(c.filtros)) == sorted([
        CriteriosICP("CO", {"ciiu": "1081", "departamento": "Antioquia"}),          # Croma
        CriteriosICP("CO", {"tipo_negocio": ("shop=bakery",), "departamento": "Antioquia"}),  # OSM, ciiu traducido
    ], key=lambda c: sorted(c.filtros))


def test_lote_es_la_busqueda_y_cada_llamada_deja_su_costo_y_cada_lead_su_cumplimiento():
    caso, repo, costos, fabrica, borrador_id = _caso()

    r = caso.ejecutar(borrador_id)

    assert r.busqueda_id == borrador_id
    assert fabrica.llamadas == [borrador_id]
    assert len(costos.filas) == 2  # una fila por fuente llamada, escrita por el adaptador
    assert {fila.lote_id for fila in costos.filas} == {borrador_id}
    assert len(repo.leads) == 2
    assert set(repo.cumplimiento) == set(repo.leads.values())  # ningún lead sin fila de cumplimiento
    assert {lote for _, _, lote in repo.lead_fuentes} == {borrador_id}


def test_solo_ejecuta_borrador():
    caso, repo, costos, fabrica, borrador_id = _caso()
    caso.ejecutar(borrador_id)
    filas, llamadas = len(costos.filas), len(fabrica.llamadas)

    with pytest.raises(BusquedaYaEjecutada):
        caso.ejecutar(borrador_id)

    assert (len(costos.filas), len(fabrica.llamadas)) == (filas, llamadas)  # la segunda no llamó a nadie


def test_pierde_la_carrera_por_el_borrador_no_llama_a_ninguna_fuente():
    class OtroGanoLaTransicion(RepositorioLeadsFalso):
        def pasar_a_ejecutando(self, busqueda_id):
            return False  # entre obtener_borrador y la transición, otra petición ya la hizo

    caso, repo, costos, fabrica, borrador_id = _caso(repo=OtroGanoLaTransicion())

    with pytest.raises(BusquedaYaEjecutada):
        caso.ejecutar(borrador_id)

    assert costos.filas == [] and fabrica.criterios_recibidos == []


def test_estado_final_completada_si_una_fuente_respondio_y_error_si_fallaron_todas():
    caso, repo, _, _, borrador_id = _caso(errores={"osm_overpass": FuenteNoDisponible()})
    r = caso.ejecutar(borrador_id)
    assert repo.busquedas[borrador_id] == "completada"
    assert set(r.errores) == {"osm_overpass"}  # el error por fuente viaja en la respuesta

    caso, repo, _, _, borrador_id = _caso(errores={"osm_overpass": FuenteNoDisponible(),
                                                   "croma_supersociedades_co": FuenteNoDisponible()})
    caso.ejecutar(borrador_id)
    assert repo.busquedas[borrador_id] == "error"
