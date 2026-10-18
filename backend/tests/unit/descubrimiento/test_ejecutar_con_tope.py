"""T026 [MIN]: ejecutar un borrador guardado. El tope (y las palabras clave) son Pulido; acá solo lo que el [MIN] necesita
y lo que protege costos y cumplimiento: una ejecución por borrador, criterios congelados, lote = búsqueda, estado final."""
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBorrador
from app.modulos.descubrimiento.dominio.errores import BusquedaNoEncontrada, BusquedaYaEjecutada, FuenteNoDisponible
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


def _empresa(fuente, nit, titular="juridica"):
    return EmpresaCruda(pais="CO", nombre=f"EMPRESA {nit} SAS", fuente=fuente, url_origen=f"https://{fuente}.test/{nit}",
                        as_of=AS_OF, actividad=Actividad("1081", "CIIU"), id_fiscal=nit, tipo_titular=titular)


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

    assert fabrica.criterios_por_fuente == {
        "croma_supersociedades_co": CriteriosICP("CO", {"ciiu": "1081", "departamento": "Antioquia"}),
        "osm_overpass": CriteriosICP("CO", {"tipo_negocio": ("shop=bakery",), "departamento": "Antioquia"}),  # ciiu traducido
    }


def test_lote_es_la_busqueda_y_cada_llamada_deja_su_costo_y_cada_lead_su_cumplimiento():
    empresas = {"croma_supersociedades_co": (_empresa("croma_supersociedades_co", "900000001"),
                                             _empresa("croma_supersociedades_co", "800000003", titular="natural")),
                "osm_overpass": (_empresa("osm_overpass", "900000002"),)}
    caso, repo, costos, fabrica, borrador_id = _caso(empresas=empresas)

    r = caso.ejecutar(borrador_id)

    assert r.busqueda_id == borrador_id
    assert fabrica.llamadas == [borrador_id]
    assert len(costos.filas) == 2  # una fila por fuente llamada, escrita por el adaptador
    assert {fila.lote_id for fila in costos.filas} == {borrador_id}
    assert len(repo.leads) == 3  # la natural también se guarda (embudo), y también lleva su cumplimiento
    # Cada lead, con la fuente, la licencia y el origen de SU empresa: ni la de otra fuente ni una inventada.
    for e in (e for por_fuente in empresas.values() for e in por_fuente):
        lead_id = repo.leads[("CO", e.id_fiscal)]
        assert repo.cumplimiento[lead_id] == (e.fuente, f"lic_{e.fuente}", e.url_origen, AS_OF)
    assert set(repo.cumplimiento) == set(repo.leads.values())
    assert {lote for _, _, lote in repo.lead_fuentes} == {borrador_id}


def test_mismo_nit_en_dos_fuentes_es_un_lead_con_un_cumplimiento_y_dos_lead_fuentes():
    empresas = {"croma_supersociedades_co": (_empresa("croma_supersociedades_co", "900.000.001-5"),),
                "osm_overpass": (_empresa("osm_overpass", "900000001"),)}
    caso, repo, _, _, borrador_id = _caso(empresas=empresas)

    r = caso.ejecutar(borrador_id)

    assert len(repo.leads) == 1 and len(repo.cumplimiento) == 1
    assert {fuente for _, fuente, _ in repo.lead_fuentes} == {"croma_supersociedades_co", "osm_overpass"}
    assert len(repo.lead_fuentes) == 2
    assert (r.encontrados, r.unicos, r.nuevos) == (2, 1, 1)


def test_solo_ejecuta_borrador():
    caso, repo, costos, fabrica, borrador_id = _caso()
    caso.ejecutar(borrador_id)
    filas, llamadas = len(costos.filas), len(fabrica.llamadas)

    with pytest.raises(BusquedaYaEjecutada):
        caso.ejecutar(borrador_id)

    assert (len(costos.filas), len(fabrica.llamadas)) == (filas, llamadas)  # la segunda no llamó a nadie
    assert repo.busquedas[borrador_id] == "completada"  # y no tocó el estado que dejó la primera


def test_busqueda_inexistente_o_ajena_es_no_encontrada_y_no_llama_a_nadie():
    caso, repo, costos, fabrica, _ = _caso()

    with pytest.raises(BusquedaNoEncontrada):  # no BusquedaYaEjecutada: el router distingue 404 de 409
        caso.ejecutar(uuid4())

    assert costos.filas == [] and fabrica.llamadas == []


def test_pierde_la_carrera_por_el_borrador_no_llama_a_ninguna_fuente():
    class OtroGanoLaTransicion(RepositorioLeadsFalso):
        def pasar_a_ejecutando(self, busqueda_id):
            return False  # entre obtener_borrador y la transición, otra petición ya la hizo

    caso, repo, costos, fabrica, borrador_id = _caso(repo=OtroGanoLaTransicion())

    with pytest.raises(BusquedaYaEjecutada):
        caso.ejecutar(borrador_id)

    assert costos.filas == [] and fabrica.criterios_por_fuente == {}
    assert repo.busquedas[borrador_id] == "borrador"  # el que pierde no toca la búsqueda del ganador


def test_estado_final_completada_si_una_fuente_respondio_y_error_si_fallaron_todas():
    caso, repo, _, _, borrador_id = _caso(errores={"osm_overpass": FuenteNoDisponible()})
    r = caso.ejecutar(borrador_id)
    assert repo.busquedas[borrador_id] == "completada"
    assert set(r.errores) == {"osm_overpass"}  # el error por fuente viaja en la respuesta

    caso, repo, _, _, borrador_id = _caso(errores={"osm_overpass": FuenteNoDisponible(),
                                                   "croma_supersociedades_co": FuenteNoDisponible()})
    caso.ejecutar(borrador_id)
    assert repo.busquedas[borrador_id] == "error"


def test_ninguna_fuente_cubre_el_icp_termina_completada_sin_llamar_a_nadie():
    caso, repo, costos, fabrica, _ = _caso()
    pe = CriteriosICP(pais="PE", filtros={"ciiu": "1081", "departamento": "Lima"})
    borrador_id = repo.crear_borrador(pe, None, Decimal("1"), None)

    r = caso.ejecutar(borrador_id)

    assert repo.busquedas[borrador_id] == "completada"
    assert r.sin_fuente_para == ("PE", pe.filtros)
    assert costos.filas == [] and fabrica.criterios_por_fuente == {}
    assert repo.leads == {}
