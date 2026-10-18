"""T026: ejecutar un borrador guardado. Una ejecución por borrador, criterios congelados, lote = búsqueda, estado final y
el TOPE DE GASTO (revisión del advisor: costos). Las palabras clave son Pulido (T022-T023)."""
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBorrador
from app.modulos.descubrimiento.dominio.errores import (
    LimiteFuenteAgotado,
    BusquedaNoEncontrada,
    BusquedaYaEjecutada,
    CriterioNoSoportado,
    FuenteNoDisponible,
    TopeExcedido,
)
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda, MetaFuente
from tests.falsos import FabricaFalsa, RegistroCostosFalso, RepositorioLeadsFalso

AS_OF = datetime(2026, 10, 1, tzinfo=UTC)


def _meta(clave, filtros, costo_maximo_llamada):
    return MetaFuente(clave=clave, proveedor=clave.split("_")[0], paises=frozenset({"CO"}), filtros=frozenset(filtros),
                      trae=frozenset({"nombre"}), tipo="live", licencia=f"lic_{clave}",
                      costo_maximo_llamada=costo_maximo_llamada)


CS, OSM = Decimal("0.00099"), Decimal("0.00042")  # 1 crédito de Croma; 2 intentos x 30 s de Overpass
MAXIMO = CS + OSM  # 0.00141: lo que el caso de uso declara como peor caso de la búsqueda
METAS = {
    "croma_supersociedades_co": _meta("croma_supersociedades_co", {"ciiu", "departamento"}, CS),
    "osm_overpass": _meta("osm_overpass", {"tipo_negocio", "departamento"}, OSM),
}
ACTIVIDADES = {"1081": ("shop=bakery",)}
GUARDADOS = CriteriosICP(pais="CO", filtros={"ciiu": "1081", "departamento": "Antioquia"})


def _empresa(fuente, nit, titular="juridica"):
    return EmpresaCruda(pais="CO", nombre=f"EMPRESA {nit} SAS", fuente=fuente, url_origen=f"https://{fuente}.test/{nit}",
                        as_of=AS_OF, actividad=Actividad("1081", "CIIU"), id_fiscal=nit, tipo_titular=titular)


def _caso(errores=None, empresas=None, repo=None, tope=Decimal("5.00"), gasto=None, costos=None, metas=METAS, criterios=GUARDADOS):
    repo, costos = repo or RepositorioLeadsFalso(), costos or RegistroCostosFalso()
    empresas = empresas if empresas is not None else {"croma_supersociedades_co": (_empresa("croma_supersociedades_co", "900000001"),),
                                                       "osm_overpass": (_empresa("osm_overpass", "900000002"),)}
    fabrica = FabricaFalsa(costos, metas, empresas, errores, gasto)
    borrador_id = repo.crear_borrador(criterios, "email", tope, None)
    return EjecutarBorrador(repo, fabrica, ACTIVIDADES, costos), repo, costos, fabrica, borrador_id


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
    assert {fuente: lic for (_, fuente, _), lic in repo.licencia_lead_fuente.items()} == {
        "croma_supersociedades_co": "lic_croma_supersociedades_co", "osm_overpass": "lic_osm_overpass"}


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


def test_error_inesperado_deja_la_busqueda_en_error_y_no_se_traga():
    caso, repo, _, _, borrador_id = _caso(errores={"osm_overpass": RuntimeError("bug"),
                                                   "croma_supersociedades_co": RuntimeError("bug")})

    with pytest.raises(RuntimeError):
        caso.ejecutar(borrador_id)

    assert repo.busquedas[borrador_id] == "error"  # no se queda en `ejecutando` para siempre


def test_criterio_no_soportado_por_una_fuente_no_tumba_la_busqueda():
    # Pasa de verdad: datos.gov.co sin cámaras para el departamento pedido lanza CriterioNoSoportado antes de cualquier request.
    caso, repo, costos, _, borrador_id = _caso(errores={"osm_overpass": CriterioNoSoportado("sin cámaras")})

    try:
        r = caso.ejecutar(borrador_id)
    except CriterioNoSoportado as error:  # el bug: una fuente que no entiende el criterio tumba a las que sí corren
        r = error
    assert not isinstance(r, CriterioNoSoportado), "CriterioNoSoportado se propagó y la búsqueda quedó en error"

    assert repo.busquedas[borrador_id] == "completada"
    assert set(r.errores) == {"osm_overpass"} and isinstance(r.errores["osm_overpass"], CriterioNoSoportado)
    assert r.encontrados == 1


# --- tope de gasto (advisor, costos) --------------------------------------------------------------------------

def test_no_ejecuta_si_costo_maximo_supera_tope():
    # Un cien-milésimo bajo el peor caso (0.00141): ni siquiera la primera fuente se llama.
    caso, repo, costos, fabrica, borrador_id = _caso(tope=Decimal("0.00140"))

    with pytest.raises(TopeExcedido):
        caso.ejecutar(borrador_id)

    assert costos.filas == [] and fabrica.criterios_por_fuente == {}  # 0 requests, 0 filas de costo
    assert repo.busquedas[borrador_id] == "borrador"  # sigue en borrador: el usuario puede subir el tope y reintentar
    assert repo.leads == {} and repo.lead_fuentes == set()


def test_el_borde_del_tope_es_inclusivo():
    caso, repo, costos, _, borrador_id = _caso(tope=MAXIMO)  # tope == costo máximo: entra (<=, no <)

    r = caso.ejecutar(borrador_id)

    assert repo.busquedas[borrador_id] == "completada" and len(costos.filas) == 2 and r.omitidas_por_tope == ()


def test_lo_ya_gastado_en_el_lote_cuenta_para_el_costo_maximo():
    class LibroConGastoPrevio(RegistroCostosFalso):
        def gasto_busqueda(self, busqueda_id):  # lo que la vista previa ya gastó en este lote, a valor de lista
            return Decimal("0.00113") + super().gasto_busqueda(busqueda_id)

    # Alcanza para las dos fuentes solas (0.00141), no para las dos más lo ya gastado (0.00254).
    caso, repo, costos, fabrica, borrador_id = _caso(tope=Decimal("0.0020"), costos=LibroConGastoPrevio())

    with pytest.raises(TopeExcedido):
        caso.ejecutar(borrador_id)

    assert costos.filas == [] and fabrica.criterios_por_fuente == {}


def test_corta_antes_de_la_llamada_que_pasaria_el_tope():
    # Defensa en profundidad: el peor caso cabía (0.00141 <= 0.01), pero Croma terminó costando 0.0099 (10 créditos).
    # Con eso el tope alcanza para haber llamado a Croma y no para llamar a OSM: OSM no se llama.
    caso, repo, costos, fabrica, borrador_id = _caso(tope=Decimal("0.01"),
                                                    gasto={"croma_supersociedades_co": Decimal("0.0099")})

    r = caso.ejecutar(borrador_id)

    assert list(fabrica.criterios_por_fuente) == ["croma_supersociedades_co"]  # OSM nunca recibió buscar()
    assert [f.fuente for f in costos.filas] == ["croma_supersociedades_co"]  # y no dejó fila de costo
    assert r.omitidas_por_tope == ("osm_overpass",)
    assert repo.busquedas[borrador_id] == "tope_alcanzado"
    assert ("CO", "900000001") in repo.leads and ("CO", "900000002") not in repo.leads  # lo de Croma queda guardado
    assert len(repo.cumplimiento) == 1  # y con su cumplimiento


def test_si_el_tope_alcanza_justo_para_la_segunda_fuente_se_llama():
    # 0.0099 gastados + 0.00042 = 0.01032: con tope exactamente ese valor entra (<=).
    caso, repo, costos, fabrica, borrador_id = _caso(tope=Decimal("0.01032"),
                                                    gasto={"croma_supersociedades_co": Decimal("0.0099")})

    r = caso.ejecutar(borrador_id)

    assert list(fabrica.criterios_por_fuente) == ["croma_supersociedades_co", "osm_overpass"]
    assert r.omitidas_por_tope == () and repo.busquedas[borrador_id] == "completada"


def test_un_error_de_fuente_no_se_confunde_con_el_tope():
    caso, repo, _, fabrica, borrador_id = _caso(errores={"croma_supersociedades_co": FuenteNoDisponible()})

    r = caso.ejecutar(borrador_id)

    assert r.omitidas_por_tope == () and set(r.errores) == {"croma_supersociedades_co"}
    assert repo.busquedas[borrador_id] == "completada" and "osm_overpass" in fabrica.criterios_por_fuente


def test_sin_fuente_que_cubra_el_icp_no_hay_tope_que_aplicar():
    # El peor caso de cero fuentes es lo ya gastado: con el tope más bajo posible sigue siendo `completada`.
    caso, repo, costos, _, _ = _caso()
    pe = CriteriosICP(pais="PE", filtros={"ciiu": "1081", "departamento": "Lima"})
    borrador_id = repo.crear_borrador(pe, None, Decimal("0.00001"), None)

    caso.ejecutar(borrador_id)

    assert repo.busquedas[borrador_id] == "completada" and costos.filas == []


def test_ya_ejecutada_gana_sobre_tope_excedido():
    # Tope excedido Y búsqueda ya ejecutada: manda el 409 de "ya ejecutada" (no se revela ni se evalúa nada de más).
    caso, repo, _, _, borrador_id = _caso(tope=Decimal("0.00140"))
    repo.busquedas[borrador_id] = "completada"

    with pytest.raises(BusquedaYaEjecutada):
        caso.ejecutar(borrador_id)


def test_el_tope_exige_el_libro_de_costos_en_el_constructor():
    # Guarda estructural: sin `costos` obligatorio alguien arma EjecutarBorrador sin tope y gasta sin freno.
    param = inspect.signature(EjecutarBorrador.__init__).parameters["costos"]
    assert param.default is inspect.Parameter.empty


def test_el_chequeo_previo_suma_las_tres_fuentes_no_un_subconjunto_fijo():
    metas = {**METAS, "datos_gov_co_rues": _meta("datos_gov_co_rues", {"ciiu", "departamento"}, Decimal("0.00084"))}
    # 0.0020 alcanza para Croma + OSM (0.00141) y no para las tres (0.00225): mata "subconjunto fijo de claves".
    caso, repo, costos, fabrica, borrador_id = _caso(tope=Decimal("0.0020"), metas=metas)

    with pytest.raises(TopeExcedido):
        caso.ejecutar(borrador_id)
    assert costos.filas == [] and repo.busquedas[borrador_id] == "borrador"

    caso, repo, costos, fabrica, borrador_id = _caso(tope=Decimal("0.00225"), metas=metas)
    caso.ejecutar(borrador_id)
    assert len(costos.filas) == 3  # con el tope justo, corren las tres


def test_el_chequeo_previo_cuenta_solo_las_fuentes_seleccionadas():
    metas = {
        "croma_supersociedades_co": METAS["croma_supersociedades_co"],  # solo CO: no cubre PE
        "osm_overpass": MetaFuente(clave="osm_overpass", proveedor="osm", paises=frozenset({"CO", "PE"}),
                                   filtros=frozenset({"tipo_negocio", "departamento"}), trae=frozenset({"nombre"}),
                                   tipo="live", licencia="lic_osm", costo_maximo_llamada=OSM)}
    pe = CriteriosICP(pais="PE", filtros={"ciiu": "1081", "departamento": "Lima"})
    # 0.0005 cubre OSM (0.00042) y no Croma + OSM (0.00141): si sumara las no seleccionadas, daría TopeExcedido.
    caso, repo, costos, fabrica, borrador_id = _caso(tope=Decimal("0.0005"), metas=metas, criterios=pe)

    caso.ejecutar(borrador_id)

    assert list(fabrica.criterios_por_fuente) == ["osm_overpass"] and repo.busquedas[borrador_id] == "completada"


def test_limite_de_croma_que_corta_la_busqueda_termina_en_tope_alcanzado():
    # El límite (24 h o cupo mensual) es la otra cara del tope de gasto: se llegó a lo que se podía gastar.
    caso, repo, _, _, borrador_id = _caso(errores={"croma_supersociedades_co": LimiteFuenteAgotado()})

    r = caso.ejecutar(borrador_id)

    assert repo.busquedas[borrador_id] == "tope_alcanzado"
    assert set(r.errores) == {"croma_supersociedades_co"}  # y el motivo viaja por fuente, no se esconde
